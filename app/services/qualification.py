from app.models.domain import ExtractedLeadFacts, QualificationResult, RecommendedAction, ScoreBreakdown
from app.services.scoring import fit_priority


def detect_missing_information(facts: ExtractedLeadFacts) -> list[str]:
    detected: list[str] = []
    if not facts.company_name:
        detected.append("company_name")
    if facts.budget_min_usd is None and facts.budget_max_usd is None:
        detected.append("budget")
    if facts.timeline_days is None:
        detected.append("timeline")
    if not facts.current_stack:
        detected.append("current_stack")
    for item in facts.missing_information:
        if item not in detected:
            detected.append(item)
    return detected


def build_qualification(
    facts: ExtractedLeadFacts,
    score: ScoreBreakdown,
    recommended_action: RecommendedAction,
) -> QualificationResult:
    fit, priority = fit_priority(score.total)
    missing = detect_missing_information(facts)
    reasons = [
        f"budget_fit={score.budget_fit}/25",
        f"need_fit={score.need_fit}/25",
        f"timeline_fit={score.timeline_fit}/15",
        f"total={score.total}/100",
    ]
    return QualificationResult(
        score=score,
        fit=fit,
        priority=priority,
        estimated_deal_min_usd=facts.budget_min_usd,
        estimated_deal_max_usd=facts.budget_max_usd,
        missing_information=missing,
        recommended_action=recommended_action,
        reason_summary=reasons,
    )
