"""Pure deterministic lead normalization and qualification."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from .canonical import hash_object


SCHEMA_VERSION = "1"
EXPECTED_FIELDS = (
    "name",
    "email",
    "company",
    "service_needed",
    "budget_usd",
    "timeline_days",
    "message",
)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _normalize_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("form values must be strings")
    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n")
    normalized = normalized.replace("\r", "\n")
    lines = [" ".join(line.split()) for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def _parse_nonnegative_int(field: str, value: str) -> int:
    normalized = _normalize_text(value)
    try:
        parsed = int(normalized, 10)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a whole number") from error
    if parsed < 0:
        raise ValueError(f"{field} must be nonnegative")
    return parsed


def normalize_form(form: Mapping[str, str]) -> dict[str, Any]:
    """Normalize only the frozen local-form fields and validate their types."""

    missing = [field for field in EXPECTED_FIELDS if field not in form]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    normalized: dict[str, Any] = {
        "name": _normalize_text(form["name"]),
        "email": _normalize_text(form["email"]).lower(),
        "company": _normalize_text(form["company"]),
        "service_needed": _normalize_text(form["service_needed"]),
        "budget_usd": _parse_nonnegative_int("budget_usd", form["budget_usd"]),
        "timeline_days": _parse_nonnegative_int(
            "timeline_days", form["timeline_days"]
        ),
        "message": _normalize_text(form["message"]),
        "source": "local_form",
        "schema_version": SCHEMA_VERSION,
    }
    if not normalized["name"]:
        raise ValueError("name must not be empty")
    if not normalized["service_needed"]:
        raise ValueError("service_needed must not be empty")
    return normalized


def _budget_score(budget_usd: int) -> tuple[int, str, str]:
    if budget_usd >= 15_000:
        return 40, "BUDGET_HIGH_TICKET", "Budget meets the high-ticket threshold."
    if budget_usd >= 5_000:
        return 30, "BUDGET_STRONG", "Budget supports a substantial engagement."
    if budget_usd >= 1_500:
        return 20, "BUDGET_PILOT", "Budget supports the fixed pilot hypothesis."
    return 0, "BUDGET_BELOW_PILOT", "Budget is below the pilot threshold."


def _timeline_score(timeline_days: int) -> tuple[int, str, str]:
    if timeline_days <= 30:
        return 20, "TIMELINE_NEAR_TERM", "The requested timeline is near term."
    if timeline_days <= 90:
        return 10, "TIMELINE_MEDIUM_TERM", "The requested timeline is within 90 days."
    return 0, "TIMELINE_LONG_TERM", "The requested timeline exceeds 90 days."


def _fit_score(company: str, service_needed: str) -> tuple[int, str, str]:
    if company and service_needed:
        return 25, "FIT_COMPANY_AND_NEED", "Company and service need are explicit."
    if service_needed:
        return 10, "FIT_NEED_ONLY", "The service need is explicit but company is missing."
    return 0, "FIT_UNCLEAR", "The service need is unclear."


def _contact_score(email: str) -> tuple[int, str, str]:
    if _EMAIL_RE.fullmatch(email):
        return 15, "CONTACT_EMAIL_VALID", "A syntactically valid email is available."
    return 0, "CONTACT_EMAIL_INVALID", "The email is not syntactically valid."


def _decision(score: int) -> tuple[str, str]:
    if score >= 70:
        return "QUALIFIED", "SCHEDULE_DISCOVERY_CALL"
    if score >= 40:
        return "REVIEW", "HUMAN_REVIEW"
    return "DISQUALIFIED", "SEND_POLITE_DECLINE"


def _response_draft(name: str, decision: str, service_needed: str) -> str:
    if decision == "QUALIFIED":
        body = (
            f"Thanks for reaching out about {service_needed}. "
            "Your request looks like a strong fit. The proposed next step is a discovery call."
        )
    elif decision == "REVIEW":
        body = (
            f"Thanks for reaching out about {service_needed}. "
            "We are reviewing the details and will confirm the best next step."
        )
    else:
        body = (
            f"Thanks for reaching out about {service_needed}. "
            "The current request does not match the pilot criteria, but we appreciate the context."
        )
    return f"Hi {name},\n\n{body}\n\nBest,\nSEN Factory"


def build_candidate(normalized: Mapping[str, Any]) -> dict[str, Any]:
    """Build the frozen, fully deterministic lead decision candidate."""

    extracted = {
        "name": normalized["name"],
        "email": normalized["email"],
        "company": normalized["company"],
        "service_needed": normalized["service_needed"],
        "budget_usd": normalized["budget_usd"],
        "timeline_days": normalized["timeline_days"],
        "message": normalized["message"],
        "schema_version": SCHEMA_VERSION,
    }
    components = (
        _budget_score(extracted["budget_usd"]),
        _timeline_score(extracted["timeline_days"]),
        _fit_score(extracted["company"], extracted["service_needed"]),
        _contact_score(extracted["email"]),
    )
    score = sum(component[0] for component in components)
    decision, next_action = _decision(score)
    qualification = {
        "score": score,
        "decision": decision,
        "next_action": next_action,
        "reason_codes": [component[1] for component in components],
        "explanation": [component[2] for component in components],
        "policy_version": "qualification_policy_v1",
    }
    candidate: dict[str, Any] = {
        "schema_version": "lead_decision_candidate_v1",
        "normalized_lead": dict(normalized),
        "extracted_lead": extracted,
        "qualification": qualification,
        "response_draft": _response_draft(
            extracted["name"], decision, extracted["service_needed"]
        ),
    }
    candidate["candidate_sha256"] = hash_object(candidate)
    return candidate
