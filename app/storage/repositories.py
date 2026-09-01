from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from app.errors import LifecycleConflictError, NotFoundError
from app.models.domain import (
    Draft,
    DraftStatus,
    Event,
    ExtractedLeadFacts,
    Lead,
    LeadStatus,
    QualificationResult,
)
from app.models.persistence import LeadDetailRecord, LeadSummaryRecord
from app.storage.database import SCHEMA, connect


class LeadStore(Protocol):
    def initialize(self) -> None: ...
    def utc_now(self) -> datetime: ...
    def create_lead(self, *, lead_id: UUID, raw_text: str, source: str) -> None: ...
    def set_lead_status(self, lead_id: UUID, status: LeadStatus) -> None: ...
    def save_analysis(self, lead_id: UUID, facts: ExtractedLeadFacts, qualification: QualificationResult) -> None: ...
    def save_draft(self, draft: Draft) -> None: ...
    def get_draft(self, lead_id: UUID) -> Draft | None: ...
    def set_draft_status(self, lead_id: UUID, status: DraftStatus, reviewed_at: datetime) -> Draft: ...
    def append_event(self, lead_id: UUID, event_type: str, payload_json: str | None = None) -> Event: ...
    def get_lead_detail(self, lead_id: UUID) -> LeadDetailRecord | None: ...
    def list_lead_summaries(self) -> list[LeadSummaryRecord]: ...
    def list_events(self, lead_id: UUID) -> list[Event]: ...
    def review_draft_atomically(
        self,
        *,
        lead_id: UUID,
        draft_status: DraftStatus,
        lead_status: LeadStatus,
        reviewed_at: datetime,
        event_type: str,
    ) -> None: ...


class SQLiteLeadStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def initialize(self) -> None:
        with connect(self.path) as connection:
            connection.executescript(SCHEMA)

    def create_lead(self, *, lead_id: UUID, raw_text: str, source: str) -> None:
        now = self.utc_now()
        with connect(self.path) as connection:
            connection.execute(
                "INSERT INTO leads(id, raw_text, source, created_at, status) VALUES (?, ?, ?, ?, ?)",
                (str(lead_id), raw_text, source, now.isoformat(), LeadStatus.RECEIVED.value),
            )

    def set_lead_status(self, lead_id: UUID, status: LeadStatus) -> None:
        with connect(self.path) as connection:
            cursor = connection.execute(
                "UPDATE leads SET status = ? WHERE id = ?",
                (status.value, str(lead_id)),
            )
            if cursor.rowcount != 1:
                raise NotFoundError("Lead was not found.")

    def save_analysis(
        self,
        lead_id: UUID,
        facts: ExtractedLeadFacts,
        qualification: QualificationResult,
    ) -> None:
        with connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO analyses(lead_id, facts_json, qualification_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lead_id) DO UPDATE SET
                    facts_json = excluded.facts_json,
                    qualification_json = excluded.qualification_json,
                    created_at = excluded.created_at
                """,
                (
                    str(lead_id),
                    facts.model_dump_json(),
                    qualification.model_dump_json(),
                    self.utc_now().isoformat(),
                ),
            )

    def save_draft(self, draft: Draft) -> None:
        with connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO drafts(id, lead_id, body, status, created_at, reviewed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(draft.id),
                    str(draft.lead_id),
                    draft.body,
                    draft.status.value,
                    draft.created_at.isoformat(),
                    draft.reviewed_at.isoformat() if draft.reviewed_at else None,
                ),
            )

    def _draft_from_row(self, row) -> Draft:
        return Draft(
            id=UUID(row["id"]),
            lead_id=UUID(row["lead_id"]),
            body=row["body"],
            status=DraftStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None,
        )

    def get_draft(self, lead_id: UUID) -> Draft | None:
        with connect(self.path) as connection:
            row = connection.execute(
                "SELECT * FROM drafts WHERE lead_id = ?",
                (str(lead_id),),
            ).fetchone()
        return None if row is None else self._draft_from_row(row)

    def set_draft_status(self, lead_id: UUID, status: DraftStatus, reviewed_at: datetime) -> Draft:
        with connect(self.path) as connection:
            cursor = connection.execute(
                "UPDATE drafts SET status = ?, reviewed_at = ? WHERE lead_id = ?",
                (status.value, reviewed_at.isoformat(), str(lead_id)),
            )
            if cursor.rowcount != 1:
                raise NotFoundError("Draft was not found.")
        draft = self.get_draft(lead_id)
        assert draft is not None
        return draft

    def append_event(self, lead_id: UUID, event_type: str, payload_json: str | None = None) -> Event:
        event = Event(
            id=uuid4(),
            lead_id=lead_id,
            event_type=event_type,
            payload_json=payload_json,
            created_at=self.utc_now(),
        )
        with connect(self.path) as connection:
            connection.execute(
                "INSERT INTO events(id, lead_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    str(event.id),
                    str(event.lead_id),
                    event.event_type,
                    event.payload_json,
                    event.created_at.isoformat(),
                ),
            )
        return event

    def _lead_from_row(self, row) -> Lead:
        return Lead(
            id=UUID(row["id"]),
            raw_text=row["raw_text"],
            source=row["source"],
            created_at=datetime.fromisoformat(row["created_at"]),
            status=LeadStatus(row["status"]),
        )

    def get_lead_detail(self, lead_id: UUID) -> LeadDetailRecord | None:
        with connect(self.path) as connection:
            lead_row = connection.execute(
                "SELECT * FROM leads WHERE id = ?", (str(lead_id),)
            ).fetchone()
            if lead_row is None:
                return None
            analysis_row = connection.execute(
                "SELECT * FROM analyses WHERE lead_id = ?", (str(lead_id),)
            ).fetchone()
            draft_row = connection.execute(
                "SELECT * FROM drafts WHERE lead_id = ?", (str(lead_id),)
            ).fetchone()

        facts = None
        qualification = None
        if analysis_row is not None:
            facts = ExtractedLeadFacts.model_validate_json(analysis_row["facts_json"])
            qualification = QualificationResult.model_validate_json(analysis_row["qualification_json"])

        return LeadDetailRecord(
            lead=self._lead_from_row(lead_row),
            facts=facts,
            qualification=qualification,
            draft=None if draft_row is None else self._draft_from_row(draft_row),
        )

    def list_lead_summaries(self) -> list[LeadSummaryRecord]:
        with connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT l.*, a.facts_json, a.qualification_json
                FROM leads AS l
                LEFT JOIN analyses AS a ON a.lead_id = l.id
                ORDER BY l.created_at DESC
                """
            ).fetchall()

        summaries: list[LeadSummaryRecord] = []
        for row in rows:
            facts = ExtractedLeadFacts.model_validate_json(row["facts_json"]) if row["facts_json"] else None
            qualification = (
                QualificationResult.model_validate_json(row["qualification_json"])
                if row["qualification_json"] else None
            )
            summaries.append(
                LeadSummaryRecord(
                    lead=self._lead_from_row(row),
                    company_name=facts.company_name if facts else None,
                    score=qualification.score.total if qualification else None,
                    priority=qualification.priority.value if qualification else None,
                )
            )
        return summaries

    def list_events(self, lead_id: UUID) -> list[Event]:
        with connect(self.path) as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE lead_id = ? ORDER BY created_at ASC",
                (str(lead_id),),
            ).fetchall()
        return [
            Event(
                id=UUID(row["id"]),
                lead_id=UUID(row["lead_id"]),
                event_type=row["event_type"],
                payload_json=row["payload_json"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def review_draft_atomically(
        self,
        *,
        lead_id: UUID,
        draft_status: DraftStatus,
        lead_status: LeadStatus,
        reviewed_at: datetime,
        event_type: str,
    ) -> None:
        event_id = uuid4()
        with connect(self.path) as connection:
            draft = connection.execute(
                "SELECT status FROM drafts WHERE lead_id = ?",
                (str(lead_id),),
            ).fetchone()
            if draft is None:
                raise NotFoundError("Draft was not found.")
            if draft["status"] != DraftStatus.PENDING.value:
                raise LifecycleConflictError("Draft has already been reviewed.")
            connection.execute(
                "UPDATE drafts SET status = ?, reviewed_at = ? WHERE lead_id = ?",
                (draft_status.value, reviewed_at.isoformat(), str(lead_id)),
            )
            connection.execute(
                "UPDATE leads SET status = ? WHERE id = ?",
                (lead_status.value, str(lead_id)),
            )
            connection.execute(
                "INSERT INTO events(id, lead_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(event_id), str(lead_id), event_type, None, reviewed_at.isoformat()),
            )
