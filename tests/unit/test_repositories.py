from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models.domain import Draft, DraftStatus, LeadStatus
from app.services.qualification import build_qualification
from app.services.recommendation import recommend_action
from app.services.scoring import score_lead
from app.storage.repositories import SQLiteLeadStore
from tests.unit.test_qualification import make_facts


def test_lead_persists_across_store_instances(tmp_path: Path) -> None:
    db = tmp_path / "leads.db"
    lead_id = uuid4()
    store = SQLiteLeadStore(db)
    store.initialize()
    store.create_lead(lead_id=lead_id, raw_text="A realistic inbound lead message", source="website")
    store.set_lead_status(lead_id, LeadStatus.PROCESSING)

    facts = make_facts()
    score = score_lead(facts)
    qualification = build_qualification(facts, score, recommend_action(facts, score))
    store.save_analysis(lead_id, facts, qualification)
    draft = Draft(
        id=uuid4(), lead_id=lead_id, body="Thanks for reaching out.",
        status=DraftStatus.PENDING, created_at=datetime.now(timezone.utc),
    )
    store.save_draft(draft)
    store.append_event(lead_id, "lead_received")
    store.append_event(lead_id, "draft_created")

    reopened = SQLiteLeadStore(db)
    reopened.initialize()
    detail = reopened.get_lead_detail(lead_id)

    assert detail is not None
    assert detail.lead.id == lead_id
    assert detail.lead.status == LeadStatus.PROCESSING
    assert detail.facts is not None and detail.facts.need == "AI support agent"
    assert detail.draft is not None and detail.draft.status == DraftStatus.PENDING
    assert [e.event_type for e in reopened.list_events(lead_id)] == ["lead_received", "draft_created"]


def test_list_lead_summaries_is_newest_first(tmp_path: Path) -> None:
    db = tmp_path / "leads.db"
    store = SQLiteLeadStore(db)
    store.initialize()
    older = uuid4()
    newest = uuid4()
    times = iter([
        datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
    ])
    store.utc_now = lambda: next(times)  # type: ignore[method-assign]
    store.create_lead(lead_id=older, raw_text="Older realistic lead", source="website")
    store.create_lead(lead_id=newest, raw_text="Newest realistic lead", source="website")

    assert store.list_lead_summaries()[0].lead.id == newest
