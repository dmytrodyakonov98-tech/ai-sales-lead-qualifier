import json
from uuid import uuid4

from app.models.domain import Draft, DraftStatus, LeadStatus
from app.services.qualification import build_qualification
from app.services.recommendation import recommend_action
from app.services.scoring import score_lead


class LeadPipeline:
    def __init__(self, *, store, extractor, drafter) -> None:
        self.store = store
        self.extractor = extractor
        self.drafter = drafter

    async def process(self, raw_text: str):
        lead_id = uuid4()
        self.store.create_lead(lead_id=lead_id, raw_text=raw_text, source="website")
        self.store.append_event(lead_id, "lead_received")
        try:
            self.store.set_lead_status(lead_id, LeadStatus.PROCESSING)
            self.store.append_event(lead_id, "extraction_started")
            facts = await self.extractor.extract(raw_text)
            self.store.append_event(lead_id, "extraction_completed")

            score = score_lead(facts)
            action = recommend_action(facts, score)
            qualification = build_qualification(facts, score, action)
            self.store.save_analysis(lead_id, facts, qualification)
            self.store.set_lead_status(lead_id, LeadStatus.QUALIFIED)
            self.store.append_event(lead_id, "qualification_completed", qualification.model_dump_json())

            body = await self.drafter.draft(raw_text, facts, qualification)
            draft = Draft(id=uuid4(), lead_id=lead_id, body=body, status=DraftStatus.PENDING, created_at=self.store.utc_now())
            self.store.save_draft(draft)
            self.store.append_event(lead_id, "draft_created")
            self.store.set_lead_status(lead_id, LeadStatus.NEEDS_REVIEW)
            detail = self.store.get_lead_detail(lead_id)
            assert detail is not None
            return detail
        except Exception as exc:
            self.store.set_lead_status(lead_id, LeadStatus.FAILED)
            self.store.append_event(lead_id, "pipeline_failed", json.dumps({"error_type": type(exc).__name__}))
            raise
