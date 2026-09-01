import json

from app.errors import LLMDraftingError
from app.llm.client import LLMClient
from app.models.domain import ExtractedLeadFacts, QualificationResult


class ResponseDrafter:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def draft(self, raw_text: str, facts: ExtractedLeadFacts, qualification: QualificationResult) -> str:
        context = json.dumps({
            "original_lead": raw_text,
            "facts": facts.model_dump(mode="json"),
            "qualification": qualification.model_dump(mode="json"),
        })
        try:
            result = await self.client.draft_reply(context)
            body = result.body.strip()
            if not body:
                raise ValueError("draft body is blank")
            return body
        except Exception as exc:
            raise LLMDraftingError("Lead response draft could not be completed.") from exc
