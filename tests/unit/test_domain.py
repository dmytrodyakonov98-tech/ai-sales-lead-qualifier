import pytest
from pydantic import ValidationError

from app.models.domain import ExtractedLeadFacts, ScoreBreakdown


def facts(**overrides):
    values = {
        "contact_name": None,
        "company_name": "Acme",
        "company_size": 30,
        "industry": "SaaS",
        "current_stack": None,
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
    values.update(overrides)
    return ExtractedLeadFacts(**values)


def test_budget_range_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        facts(budget_min_usd=12_000, budget_max_usd=8_000)


def test_timeline_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        facts(timeline_days=0)


def test_need_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        facts(need="   ")


def test_score_total_must_equal_components() -> None:
    with pytest.raises(ValidationError):
        ScoreBreakdown(
            budget_fit=25,
            need_fit=25,
            timeline_fit=15,
            decision_intent=15,
            project_clarity=10,
            company_fit=10,
            total=99,
        )
