"""SQLite WAL persistence for the M001-B001 current state and audit trail."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes


_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    candidate_sha256 TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    document_type TEXT NOT NULL,
    revision INTEGER NOT NULL,
    content_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, document_type, revision)
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id),
    candidate_sha256 TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crm_inbox (
    crm_record_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id),
    approval_id TEXT NOT NULL UNIQUE REFERENCES approvals(approval_id),
    lead_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id),
    artifact_kind TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    cas_ref TEXT NOT NULL,
    approval_id TEXT NOT NULL REFERENCES approvals(approval_id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    evidence_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    input_hashes_json TEXT NOT NULL,
    output_hashes_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    subject_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _json_text(value: Any) -> str:
    return canonical_bytes(value).decode("utf-8")


def _decode(value: str) -> Any:
    return json.loads(value)


class Database:
    """One process-local repository around a WAL-mode SQLite database."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("database is not initialized")
        return self._connection

    def initialize(self) -> None:
        with self._lock:
            if self._connection is not None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self.path,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) "
                "VALUES (1, '2026-09-02T00:00:00+00:00')"
            )
            self._connection = connection

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self.connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def journal_mode(self) -> str:
        with self._lock:
            row = self.connection.execute("PRAGMA journal_mode").fetchone()
            return str(row[0]).lower()

    def insert_run(
        self, connection: sqlite3.Connection, run: Mapping[str, Any]
    ) -> None:
        connection.execute(
            "INSERT INTO runs(run_id, state, candidate_sha256, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                run["run_id"],
                run["state"],
                run.get("candidate_sha256"),
                run["created_at"],
                run["updated_at"],
            ),
        )

    def insert_document(
        self, connection: sqlite3.Connection, document: Mapping[str, Any]
    ) -> None:
        connection.execute(
            "INSERT INTO documents(document_id, run_id, document_type, revision, "
            "content_json, content_sha256, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                document["document_id"],
                document["run_id"],
                document["document_type"],
                document["revision"],
                _json_text(document["content"]),
                document["content_sha256"],
                document["created_at"],
            ),
        )

    def update_run_state(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        state: str,
        updated_at: str,
    ) -> None:
        cursor = connection.execute(
            "UPDATE runs SET state = ?, updated_at = ? WHERE run_id = ?",
            (state, updated_at, run_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(run_id)

    def insert_approval(
        self, connection: sqlite3.Connection, approval: Mapping[str, Any]
    ) -> None:
        connection.execute(
            "INSERT INTO approvals(approval_id, run_id, candidate_sha256, actor_id, "
            "decision, decided_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                approval["approval_id"],
                approval["run_id"],
                approval["candidate_sha256"],
                approval["actor_id"],
                approval["decision"],
                approval["decided_at"],
            ),
        )

    def insert_crm_record(
        self, connection: sqlite3.Connection, record: Mapping[str, Any]
    ) -> None:
        connection.execute(
            "INSERT INTO crm_inbox(crm_record_id, run_id, approval_id, lead_json, "
            "created_at) VALUES (?, ?, ?, ?, ?)",
            (
                record["crm_record_id"],
                record["run_id"],
                record["approval_id"],
                _json_text(record["lead"]),
                record["created_at"],
            ),
        )

    def insert_artifact(
        self, connection: sqlite3.Connection, artifact: Mapping[str, Any]
    ) -> None:
        connection.execute(
            "INSERT INTO artifacts(artifact_id, run_id, artifact_kind, content_sha256, "
            "cas_ref, approval_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                artifact["artifact_id"],
                artifact["run_id"],
                artifact["artifact_kind"],
                artifact["content_sha256"],
                artifact["cas_ref"],
                artifact["approval_id"],
                artifact["created_at"],
            ),
        )

    def append_evidence(
        self, connection: sqlite3.Connection, evidence: Mapping[str, Any]
    ) -> None:
        connection.execute(
            "INSERT INTO evidence(evidence_id, run_id, evidence_type, subject_id, "
            "input_hashes_json, output_hashes_json, metadata_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                evidence["evidence_id"],
                evidence["run_id"],
                evidence["evidence_type"],
                evidence["subject_id"],
                _json_text(evidence["input_hashes"]),
                _json_text(evidence["output_hashes"]),
                _json_text(evidence["metadata"]),
                evidence["created_at"],
            ),
        )

    def append_event(
        self, connection: sqlite3.Connection, event: Mapping[str, Any]
    ) -> None:
        connection.execute(
            "INSERT INTO events(event_id, run_id, event_type, actor_type, actor_id, "
            "subject_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event["event_id"],
                event["run_id"],
                event["event_type"],
                event["actor_type"],
                event.get("actor_id"),
                event["subject_id"],
                _json_text(event["payload"]),
                event["created_at"],
            ),
        )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT run_id, state, candidate_sha256, created_at, updated_at "
                "FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_document(
        self, run_id: str, document_type: str, revision: int = 1
    ) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT document_id, run_id, document_type, revision, content_json, "
                "content_sha256, created_at FROM documents "
                "WHERE run_id = ? AND document_type = ? AND revision = ?",
                (run_id, document_type, revision),
            ).fetchone()
        if row is None:
            return None
        return {
            "document_id": row["document_id"],
            "run_id": row["run_id"],
            "document_type": row["document_type"],
            "revision": row["revision"],
            "content": _decode(row["content_json"]),
            "content_sha256": row["content_sha256"],
            "created_at": row["created_at"],
        }

    def get_approval(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT approval_id, run_id, candidate_sha256, actor_id, decision, "
                "decided_at FROM approvals WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_crm_record(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT crm_record_id, run_id, approval_id, lead_json, created_at "
                "FROM crm_inbox WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "crm_record_id": row["crm_record_id"],
            "run_id": row["run_id"],
            "approval_id": row["approval_id"],
            "lead": _decode(row["lead_json"]),
            "created_at": row["created_at"],
        }

    def get_artifact(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT artifact_id, run_id, artifact_kind, content_sha256, cas_ref, "
                "approval_id, created_at FROM artifacts WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def evidence_types(self, run_id: str) -> list[str]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT evidence_type FROM evidence WHERE run_id = ? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        return [str(row["evidence_type"]) for row in rows]

    def event_types(self, run_id: str) -> list[str]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT event_type FROM events WHERE run_id = ? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        return [str(row["event_type"]) for row in rows]

    def count_crm_rows(self, run_id: str) -> int:
        return self._count("crm_inbox", run_id)

    def count_artifacts(self, run_id: str) -> int:
        return self._count("artifacts", run_id)

    def count_approvals(self, run_id: str) -> int:
        return self._count("approvals", run_id)

    def _count(self, table: str, run_id: str) -> int:
        if table not in {"approvals", "crm_inbox", "artifacts"}:
            raise ValueError("unsupported count table")
        with self._lock:
            row = self.connection.execute(
                f"SELECT COUNT(*) AS count FROM {table} WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return int(row["count"])
