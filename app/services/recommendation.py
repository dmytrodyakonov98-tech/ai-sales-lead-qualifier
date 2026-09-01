from app.models.domain import ExtractedLeadFacts, NeedCategory, RecommendedAction, ScoreBreakdown
from app.services.qualification import detect_missing_information


def recommend_action(facts: ExtractedLeadFacts, score: ScoreBreakdown) -> RecommendedAction:
    missing = detect_missing_information(facts)
    if facts.need_category == NeedCategory.UNRELATED_OR_UNKNOWN and score.total < 40:
        return RecommendedAction.DEPRIORITIZE
    if missing and score.total < 70:
        return RecommendedAction.REQUEST_MORE_INFORMATION
    if score.total >= 70:
        return RecommendedAction.SCHEDULE_DISCOVERY_CALL
    if 40 <= score.total <= 69 and missing:
        return RecommendedAction.REQUEST_MORE_INFORMATION
    if 40 <= score.total <= 69:
        return RecommendedAction.SEND_QUALIFIED_RESPONSE
    return RecommendedAction.DEPRIORITIZE
