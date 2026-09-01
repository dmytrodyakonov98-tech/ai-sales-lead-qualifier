import pytest

from app.models.domain import ExtractedLeadFacts, Fit, Priority
from app.services.scoring import fit_priority, score_lead


def make_facts(**overrides) -> ExtractedLeadFacts:
    data = {
        "contact_name": None,
        "company_name": "Acme",
        "company_size": 30,
        "industry": "SaaS",
        "current_stack": None,
        "need": "AI support agent",
        "need_category": "ai_automation_or_agent",
        "budget_min_usd": None,
        "budget_max_usd": None,
        "timeline_days": None,
        "decision_intent": "unknown",
        "project_clarity": "medium",
        "explicit_requirements": [],
        "pain_points": [],
        "missing_information": [],
    }
    data.update(overrides)
    return ExtractedLeadFacts(**data)


@pytest.mark.parametrize(
    ("budget", "expected"),
    [(None, 5), (999, 2), (1000, 8), (2999, 8), (3000, 14), (4999, 14),
     (5000, 20), (7999, 20), (8000, 25)],
)
def test_budget_boundaries(budget, expected) -> None:
    score = score_lead(make_facts(budget_max_usd=budget))
    assert score.budget_fit == expected


@pytest.mark.parametrize(
    ("days", "expected"),
    [(None, 5), (30, 15), (31, 12), (60, 12), (61, 8), (90, 8), (91, 5)],
)
def test_timeline_boundaries(days, expected) -> None:
    assert score_lead(make_facts(timeline_days=days)).timeline_fit == expected


@pytest.mark.parametrize(
    ("total", "fit", "priority"),
    [(39, Fit.WEAK, Priority.LOW), (40, Fit.MODERATE, Priority.MEDIUM),
     (69, Fit.MODERATE, Priority.MEDIUM), (70, Fit.STRONG, Priority.HIGH)],
)
def test_fit_priority_thresholds(total, fit, priority) -> None:
    assert fit_priority(total) == (fit, priority)


def test_total_is_sum_of_components() -> None:
    score = score_lead(make_facts(budget_max_usd=10_000, timeline_days=28, decision_intent="high", project_clarity="high"))
    assert score.total == sum([
        score.budget_fit,
        score.need_fit,
        score.timeline_fit,
        score.decision_intent,
        score.project_clarity,
        score.company_fit,
    ])


def test_repeated_scoring_is_byte_stable() -> None:
    facts = make_facts(
        budget_min_usd=8000,
        budget_max_usd=12000,
        timeline_days=28,
        decision_intent="high",
        project_clarity="high",
    )
    outputs = {score_lead(facts).model_dump_json() for _ in range(100)}
    assert len(outputs) == 1
