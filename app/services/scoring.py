from app.models.domain import (
    DecisionIntent,
    ExtractedLeadFacts,
    Fit,
    NeedCategory,
    Priority,
    ProjectClarity,
    ScoreBreakdown,
)


def _budget(value: int | None) -> int:
    if value is None:
        return 5
    if value < 1_000:
        return 2
    if value < 3_000:
        return 8
    if value < 5_000:
        return 14
    if value < 8_000:
        return 20
    return 25


def _need(category: NeedCategory) -> int:
    return {
        NeedCategory.AI_AUTOMATION_OR_AGENT: 25,
        NeedCategory.LLM_RAG_OR_AI_BACKEND: 22,
        NeedCategory.PYTHON_API_INTEGRATION: 18,
        NeedCategory.GENERAL_SOFTWARE: 10,
        NeedCategory.UNRELATED_OR_UNKNOWN: 3,
    }[category]


def _timeline(days: int | None) -> int:
    if days is None:
        return 5
    if days <= 30:
        return 15
    if days <= 60:
        return 12
    if days <= 90:
        return 8
    return 5


def _intent(value: DecisionIntent) -> int:
    return {
        DecisionIntent.HIGH: 15,
        DecisionIntent.MEDIUM: 10,
        DecisionIntent.LOW: 5,
        DecisionIntent.UNKNOWN: 3,
    }[value]


def _clarity(value: ProjectClarity) -> int:
    return {
        ProjectClarity.HIGH: 10,
        ProjectClarity.MEDIUM: 7,
        ProjectClarity.LOW: 3,
    }[value]


def _company(size: int | None) -> int:
    if size is None:
        return 4
    if size <= 4:
        return 5
    if size <= 19:
        return 7
    if size <= 199:
        return 10
    return 8


def score_lead(facts: ExtractedLeadFacts) -> ScoreBreakdown:
    budget_value = facts.budget_max_usd if facts.budget_max_usd is not None else facts.budget_min_usd
    components = {
        "budget_fit": _budget(budget_value),
        "need_fit": _need(facts.need_category),
        "timeline_fit": _timeline(facts.timeline_days),
        "decision_intent": _intent(facts.decision_intent),
        "project_clarity": _clarity(facts.project_clarity),
        "company_fit": _company(facts.company_size),
    }
    return ScoreBreakdown(**components, total=sum(components.values()))


def fit_priority(total: int) -> tuple[Fit, Priority]:
    if total < 40:
        return Fit.WEAK, Priority.LOW
    if total < 70:
        return Fit.MODERATE, Priority.MEDIUM
    return Fit.STRONG, Priority.HIGH
