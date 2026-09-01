import pytest

from app.models.domain import ExtractedLeadFacts, QualificationResult, ScoreBreakdown
from app.services.response_drafter import ResponseDrafter
from tests.fixtures.fake_llm import FakeLLMClient


@pytest.mark.asyncio
async def test_draft_returns_non_blank_body() -> None:
    fake = FakeLLMClient(draft={"body": "Thanks for reaching out. Could we schedule a discovery call?"})
    facts = ExtractedLeadFacts(
        company_name="Acme", company_size=30, industry="SaaS", current_stack="Zendesk",
        need="AI support agent", need_category="ai_automation_or_agent",
        budget_min_usd=8000, budget_max_usd=12000, timeline_days=28,
        decision_intent="high", project_clarity="high", explicit_requirements=[], pain_points=[], missing_information=[]
    )
    q = QualificationResult(
        score=ScoreBreakdown(budget_fit=25, need_fit=25, timeline_fit=15, decision_intent=15, project_clarity=10, company_fit=10, total=100),
        fit="strong", priority="high", estimated_deal_min_usd=8000, estimated_deal_max_usd=12000,
        missing_information=[], recommended_action="schedule_discovery_call", reason_summary=["total=100/100"]
    )
    body = await ResponseDrafter(fake).draft("Original lead", facts, q)
    assert "discovery call" in body.lower()
