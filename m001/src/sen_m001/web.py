"""Minimal localhost-only task-first form for M001-B001."""

from __future__ import annotations

import html
import re
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .domain import EXPECTED_FIELDS
from .service import ApprovalMismatch, LeadQualifierService
from .verifier import Verifier


_RUN_PATH = re.compile(r"^/runs/(run-[0-9a-f-]+)$")
_APPROVE_PATH = re.compile(r"^/runs/(run-[0-9a-f-]+)/approve$")
_MAX_BODY_BYTES = 16 * 1024


def _page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font: 16px system-ui; max-width: 760px; margin: 40px auto; padding: 0 20px; color: #182230; }}
    label {{ display: block; margin: 14px 0; }}
    input, textarea {{ box-sizing: border-box; width: 100%; padding: 9px; }}
    button {{ padding: 10px 18px; cursor: pointer; }}
    .status {{ padding: 12px; background: #eef4ff; border-radius: 8px; font-weight: 700; }}
    pre {{ white-space: pre-wrap; background: #f5f7fa; padding: 14px; border-radius: 8px; }}
  </style>
</head>
<body>{body}</body>
</html>""".encode("utf-8")


def _home() -> bytes:
    fields = (
        ("name", "Name", "text"),
        ("email", "Email", "email"),
        ("company", "Company", "text"),
        ("service_needed", "Service needed", "text"),
        ("budget_usd", "Budget (USD)", "number"),
        ("timeline_days", "Timeline (days)", "number"),
    )
    inputs = "".join(
        f'<label>{html.escape(label)}<input name="{name}" type="{kind}" required></label>'
        for name, label, kind in fields
    )
    body = f"""
<h1>AI Sales Lead Qualifier</h1>
<p>Submit one inbound lead for deterministic qualification.</p>
<form method="post" action="/runs">
  {inputs}
  <label>Message<textarea name="message" rows="5" required></textarea></label>
  <button type="submit">Qualify lead</button>
</form>"""
    return _page("AI Sales Lead Qualifier", body)


def _run_page(service: LeadQualifierService, run_id: str) -> bytes:
    result = service.get_run(run_id)
    state = str(result["state"])
    proof_label = ""
    if state == "COMPLETED":
        if service.cas is None:
            proof_label = "NOT VERIFIED"
        else:
            proof = Verifier(service.database, service.cas).verify(run_id)
            proof_label = "VERIFIED" if proof["valid"] else "VERIFICATION FAILED"
    approval = ""
    if state == "AWAITING_HUMAN_APPROVAL":
        approval = f"""
<form method="post" action="/runs/{html.escape(run_id)}/approve">
  <input type="hidden" name="candidate_sha256" value="{html.escape(result['candidate_sha256'])}">
  <button type="submit">Approve exact decision</button>
</form>"""
    body = f"""
<p><a href="/">New lead</a></p>
<h1>Lead result</h1>
<div class="status">{html.escape(state)} {html.escape(proof_label)}</div>
<p><strong>Score:</strong> {int(result['score'])}/100</p>
<p><strong>Decision:</strong> {html.escape(str(result['decision']))}</p>
<p><strong>Next action:</strong> {html.escape(str(result['next_action']))}</p>
<h2>Response draft</h2>
<pre>{html.escape(str(result['response_draft']))}</pre>
<details><summary>Version binding</summary><code>{html.escape(str(result['candidate_sha256']))}</code></details>
{approval}"""
    return _page("Lead result", body)


def create_server(
    service: LeadQualifierService,
    host: str = "127.0.0.1",
    port: int = 0,
) -> ThreadingHTTPServer:
    """Create the B001 server; public interfaces are deliberately prohibited."""

    if host != "127.0.0.1":
        raise ValueError("M001-B001 may bind only to 127.0.0.1")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            path = urllib.parse.urlsplit(self.path).path
            if path == "/":
                self._send_html(HTTPStatus.OK, _home())
                return
            match = _RUN_PATH.fullmatch(path)
            if match is not None:
                try:
                    body = _run_page(service, match.group(1))
                except KeyError:
                    self._send_error(HTTPStatus.NOT_FOUND, "Run not found")
                    return
                self._send_html(HTTPStatus.OK, body)
                return
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
            try:
                values = self._read_form()
            except ValueError as error:
                self._send_error(HTTPStatus.BAD_REQUEST, str(error))
                return
            path = urllib.parse.urlsplit(self.path).path
            if path == "/runs":
                form = {field: values.get(field, "") for field in EXPECTED_FIELDS}
                try:
                    result = service.submit_form(form)
                except ValueError as error:
                    self._send_error(HTTPStatus.BAD_REQUEST, str(error))
                    return
                self._redirect(f"/runs/{result['run_id']}")
                return
            match = _APPROVE_PATH.fullmatch(path)
            if match is not None:
                try:
                    service.approve(match.group(1), values.get("candidate_sha256", ""))
                except ApprovalMismatch as error:
                    self._send_error(HTTPStatus.CONFLICT, str(error))
                    return
                except KeyError:
                    self._send_error(HTTPStatus.NOT_FOUND, "Run not found")
                    return
                self._redirect(f"/runs/{match.group(1)}")
                return
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")

        def _read_form(self) -> dict[str, str]:
            if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                raise ValueError("unsupported content type")
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ValueError("invalid content length") from error
            if content_length < 0 or content_length > _MAX_BODY_BYTES:
                raise ValueError("form body exceeds 16 KiB")
            data = self.rfile.read(content_length).decode("utf-8", errors="strict")
            parsed = urllib.parse.parse_qs(data, keep_blank_values=True, max_num_fields=20)
            return {key: values[0] for key, values in parsed.items() if values}

        def _send_html(self, status: HTTPStatus, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            self._send_html(status, _page(status.phrase, f"<h1>{html.escape(message)}</h1>"))

        def _redirect(self, location: str) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)
