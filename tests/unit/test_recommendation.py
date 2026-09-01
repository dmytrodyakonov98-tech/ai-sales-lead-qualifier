from app.models.domain import ExtractedLeadFacts, RecommendedAction
from app.services.recommendation import recommend_action
from app.services.scoring import score_lead


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


def test_strong_lead_schedules_discovery_call() -> None:
    facts = make_facts()
    assert recommend_action(facts, score_lead(facts)) == RecommendedAction.SCHEDULE_DISCOVERY_CALL


def test_incomplete_sub_70_lead_requests_information() -> None:
    facts = make_facts(company_name=None, current_stack=None, budget_min_usd=None, budget_max_usd=None, timeline_days=None, decision_intent="unknown", project_clarity="low", company_size=None)
    assert recommend_action(facts, score_lead(facts)) == RecommendedAction.REQUEST_MORE_INFORMATION


def test_unrelated_weak_lead_is_deprioritized() -> None:
    facts = make_facts(need_category="unrelated_or_unknown", budget_min_usd=100, budget_max_usd=500, timeline_days=120, decision_intent="low", project_clarity="low", company_size=2)
    assert recommend_action(facts, score_lead(facts)) == RecommendedAction.DEPRIORITIZE
