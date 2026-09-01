from app.errors import LLMExtractionError
from app.llm.client import LLMClient
from app.models.domain import ExtractedLeadFacts


class LeadExtractor:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def extract(self, raw_text: str) -> ExtractedLeadFacts:
        try:
            return await self.client.extract_lead(raw_text)
        except Exception as exc:
            raise LLMExtractionError("Lead extraction could not be completed.") from exc
