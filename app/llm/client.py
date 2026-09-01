from __future__ import annotations

from typing import Protocol

from app.llm.schemas import DraftLLMOutput
from app.models.domain import ExtractedLeadFacts


class LLMClient(Protocol):
    async def extract_lead(self, raw_text: str) -> ExtractedLeadFacts: ...
    async def draft_reply(self, context_json: str) -> DraftLLMOutput: ...


class OpenAILLMClient:
    def __init__(self, *, api_key: str, model: str) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI SDK is not installed") from exc
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def extract_lead(self, raw_text: str) -> ExtractedLeadFacts:
        from app.llm.prompts import EXTRACTION_INSTRUCTIONS
        response = await self.client.responses.parse(
            model=self.model,
            instructions=EXTRACTION_INSTRUCTIONS,
            input=raw_text,
            text_format=ExtractedLeadFacts,
        )
        if response.output_parsed is None:
            raise ValueError("structured extraction was not parsed")
        return response.output_parsed

    async def draft_reply(self, context_json: str) -> DraftLLMOutput:
        from app.llm.prompts import DRAFT_INSTRUCTIONS
        response = await self.client.responses.parse(
            model=self.model,
            instructions=DRAFT_INSTRUCTIONS,
            input=context_json,
            text_format=DraftLLMOutput,
        )
        if response.output_parsed is None:
            raise ValueError("structured draft was not parsed")
        return response.output_parsed


class UnavailableLLMClient:
    async def extract_lead(self, raw_text: str) -> ExtractedLeadFacts:
        raise RuntimeError("LLM provider is not configured")

    async def draft_reply(self, context_json: str) -> DraftLLMOutput:
        raise RuntimeError("LLM provider is not configured")
