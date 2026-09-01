import pytest

from app.errors import LLMExtractionError
from app.services.extractor import LeadExtractor
from tests.fixtures.fake_llm import FakeLLMClient


@pytest.mark.asyncio
async def test_extractor_returns_validated_facts() -> None:
    fake = FakeLLMClient(extraction={
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
    })
    facts = await LeadExtractor(fake).extract("We need an AI support agent for our SaaS business.")
    assert facts.company_name == "Acme"
    assert facts.budget_max_usd == 12000


@pytest.mark.asyncio
async def test_extractor_wraps_unusable_output() -> None:
    fake = FakeLLMClient(extraction={"need": ""})
    with pytest.raises(LLMExtractionError):
        await LeadExtractor(fake).extract("This is a sufficiently long lead message.")
