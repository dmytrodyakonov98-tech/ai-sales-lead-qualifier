import pytest

from app.errors import LLMExtractionError
from app.services.extractor import LeadExtractor
from app.services.lead_pipeline import LeadPipeline
from app.services.response_drafter import ResponseDrafter
from app.storage.repositories import SQLiteLeadStore
from tests.fixtures.fake_llm import FakeLLMClient


@pytest.mark.asyncio
async def test_high_quality_lead_reaches_needs_review(tmp_path) -> None:
    fake = FakeLLMClient(
        extraction={
            "contact_name": None, "company_name": "Acme", "company_size": 30, "industry": "SaaS",
            "current_stack": "Zendesk", "need": "AI support agent", "need_category": "ai_automation_or_agent",
            "budget_min_usd": 8000, "budget_max_usd": 12000, "timeline_days": 28,
            "decision_intent": "high", "project_clarity": "high", "explicit_requirements": [],
            "pain_points": [], "missing_information": []
        },
        draft={"body": "Thanks for reaching out. Let's schedule a discovery call."},
    )
    store = SQLiteLeadStore(tmp_path / "leads.db")
    store.initialize()
    pipeline = LeadPipeline(store=store, extractor=LeadExtractor(fake), drafter=ResponseDrafter(fake))

    detail = await pipeline.process("We need an AI support agent with a $10k budget in four weeks.")

    assert detail.lead.status.value == "needs_review"
    assert detail.qualification is not None and detail.qualification.fit.value == "strong"
    assert detail.draft is not None and detail.draft.status.value == "pending"
    assert [e.event_type for e in store.list_events(detail.lead.id)] == [
        "lead_received", "extraction_started", "extraction_completed",
        "qualification_completed", "draft_created"
    ]


@pytest.mark.asyncio
async def test_malformed_extraction_marks_lead_failed(tmp_path) -> None:
    fake = FakeLLMClient(extraction_error=ValueError("bad provider output"))
    store = SQLiteLeadStore(tmp_path / "leads.db")
    store.initialize()
    pipeline = LeadPipeline(store=store, extractor=LeadExtractor(fake), drafter=ResponseDrafter(fake))

    with pytest.raises(LLMExtractionError):
        await pipeline.process("This is a realistic but malformed-provider test lead.")

    summaries = store.list_lead_summaries()
    assert summaries[0].lead.status.value == "failed"
    assert store.list_events(summaries[0].lead.id)[-1].event_type == "pipeline_failed"
    assert store.get_draft(summaries[0].lead.id) is None
