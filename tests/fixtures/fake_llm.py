from app.llm.schemas import DraftLLMOutput
from app.models.domain import ExtractedLeadFacts


GOOD_EXTRACTION = {
    "contact_name": None,
    "company_name": "Acme",
    "company_size": 30,
    "industry": "SaaS",
    "current_stack": "Zendesk",
    "need": "AI support agent",
    "need_category": "ai_automation_or_agent",
    "budget_min_usd": 8000,
    "budget_max_usd": 12000,
    "timeline_days": 28,
    "decision_intent": "high",
    "project_clarity": "high",
    "explicit_requirements": [],
    "pain_points": [],
    "missing_information": [],
}


class FakeLLMClient:
    def __init__(self, *, extraction=None, draft=None, extraction_error: Exception | None = None, draft_error: Exception | None = None):
        self.extraction = extraction
        self.draft = draft or {"body": "Thanks for reaching out."}
        self.extraction_error = extraction_error
        self.draft_error = draft_error

    async def extract_lead(self, raw_text: str) -> ExtractedLeadFacts:
        if self.extraction_error:
            raise self.extraction_error
        return ExtractedLeadFacts.model_validate(self.extraction)

    async def draft_reply(self, context_json: str) -> DraftLLMOutput:
        if self.draft_error:
            raise self.draft_error
        return DraftLLMOutput.model_validate(self.draft)
