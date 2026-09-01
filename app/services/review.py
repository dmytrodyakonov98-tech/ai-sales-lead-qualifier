from app.errors import LifecycleConflictError, NotFoundError
from app.models.domain import DraftStatus, LeadStatus


class ReviewService:
    def __init__(self, store) -> None:
        self.store = store

    def _review(self, lead_id, *, draft_status: DraftStatus, lead_status: LeadStatus, event_type: str):
        detail = self.store.get_lead_detail(lead_id)
        if detail is None or detail.draft is None:
            raise NotFoundError("Lead or draft was not found.")
        if detail.draft.status != DraftStatus.PENDING:
            raise LifecycleConflictError("Draft has already been reviewed.")

        self.store.review_draft_atomically(
            lead_id=lead_id,
            draft_status=draft_status,
            lead_status=lead_status,
            reviewed_at=self.store.utc_now(),
            event_type=event_type,
        )
        updated = self.store.get_lead_detail(lead_id)
        assert updated is not None
        return updated

    def approve(self, lead_id):
        return self._review(
            lead_id,
            draft_status=DraftStatus.APPROVED,
            lead_status=LeadStatus.APPROVED,
            event_type="draft_approved",
        )

    def reject(self, lead_id):
        return self._review(
            lead_id,
            draft_status=DraftStatus.REJECTED,
            lead_status=LeadStatus.REJECTED,
            event_type="draft_rejected",
        )
