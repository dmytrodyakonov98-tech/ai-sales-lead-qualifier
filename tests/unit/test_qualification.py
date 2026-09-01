from app.models.domain import ExtractedLeadFacts
from app.services.qualification import detect_missing_information


def make_facts(**overrides) -> ExtractedLeadFacts:
    data = {
        "contact_name": None,
        "company_name": "Acme",
        "company_size": 30,
        "industry": "SaaS",
        "current_stack": "Zendesk",
        "need": "AI support agent",
        "need_category": "ai_automation_or_agent",
        "budget_min_usd": 8_000,
        "budget_max_usd": 12_000,
        "timeline_days": 28,
        "decision_intent": "high",
        "project_clarity": "high",
        "explicit_requirements": [],
        "pain_points": [],
        "missing_information": [],
    }
    data.update(overrides)
    return ExtractedLeadFacts(**data)


def test_detects_required_decision_context() -> None:
    missing = detect_missing_information(make_facts(company_name=None, current_stack=None, budget_min_usd=None, budget_max_usd=None, timeline_days=None))
    assert missing == ["company_name", "budget", "timeline", "current_stack"]


def test_merges_llm_missing_information_without_duplicates() -> None:
    missing = detect_missing_information(make_facts(current_stack=None, missing_information=["current_stack", "decision_maker"]))
    assert missing == ["current_stack", "decision_maker"]
