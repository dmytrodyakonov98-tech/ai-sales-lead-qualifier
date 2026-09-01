from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.errors import LifecycleConflictError
from app.models.domain import Draft, DraftStatus, LeadStatus
from app.services.review import ReviewService
from app.storage.repositories import SQLiteLeadStore


@pytest.fixture
def prepared_store(tmp_path):
    store = SQLiteLeadStore(tmp_path / "review.db")
    store.initialize()
    lead_id = uuid4()
    store.create_lead(lead_id=lead_id, raw_text="A valid inbound sales lead message", source="website")
    store.set_lead_status(lead_id, LeadStatus.NEEDS_REVIEW)
    store.save_draft(
        Draft(
            id=uuid4(),
            lead_id=lead_id,
            body="Thanks for reaching out.",
            status=DraftStatus.PENDING,
            created_at=store.utc_now(),
        )
    )
    return SimpleNamespace(store=store, lead_id=lead_id)


def test_approve_pending_draft_updates_both_states(prepared_store) -> None:
    service = ReviewService(prepared_store.store)
    detail = service.approve(prepared_store.lead_id)
    assert detail.lead.status.value == "approved"
    assert detail.draft is not None and detail.draft.status.value == "approved"
    assert prepared_store.store.list_events(prepared_store.lead_id)[-1].event_type == "draft_approved"


def test_second_review_fails_closed(prepared_store) -> None:
    service = ReviewService(prepared_store.store)
    service.reject(prepared_store.lead_id)
    with pytest.raises(LifecycleConflictError):
        service.approve(prepared_store.lead_id)
