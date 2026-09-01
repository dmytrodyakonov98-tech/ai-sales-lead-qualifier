from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LeadStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    QUALIFIED = "qualified"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class NeedCategory(StrEnum):
    AI_AUTOMATION_OR_AGENT = "ai_automation_or_agent"
    LLM_RAG_OR_AI_BACKEND = "llm_rag_or_ai_backend"
    PYTHON_API_INTEGRATION = "python_api_integration"
    GENERAL_SOFTWARE = "general_software"
    UNRELATED_OR_UNKNOWN = "unrelated_or_unknown"


class DecisionIntent(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class ProjectClarity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Fit(StrEnum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendedAction(StrEnum):
    REQUEST_MORE_INFORMATION = "request_more_information"
    SCHEDULE_DISCOVERY_CALL = "schedule_discovery_call"
    SEND_QUALIFIED_RESPONSE = "send_qualified_response"
    DEPRIORITIZE = "deprioritize"


class DraftStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ExtractedLeadFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_name: str | None = None
    company_name: str | None = None
    company_size: int | None = Field(default=None, gt=0)
    industry: str | None = None
    current_stack: str | None = None
    need: str = Field(min_length=1)
    need_category: NeedCategory
    budget_min_usd: int | None = Field(default=None, ge=0)
    budget_max_usd: int | None = Field(default=None, ge=0)
    timeline_days: int | None = Field(default=None, gt=0)
    decision_intent: DecisionIntent
    project_clarity: ProjectClarity
    explicit_requirements: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_business_invariants(self) -> "ExtractedLeadFacts":
        self.need = self.need.strip()
        if not self.need:
            raise ValueError("need must not be blank")
        if (
            self.budget_min_usd is not None
            and self.budget_max_usd is not None
            and self.budget_min_usd > self.budget_max_usd
        ):
            raise ValueError("budget_min_usd must be <= budget_max_usd")
        return self


class ScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_fit: int = Field(ge=0, le=25)
    need_fit: int = Field(ge=0, le=25)
    timeline_fit: int = Field(ge=0, le=15)
    decision_intent: int = Field(ge=0, le=15)
    project_clarity: int = Field(ge=0, le=10)
    company_fit: int = Field(ge=0, le=10)
    total: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def total_matches_components(self) -> "ScoreBreakdown":
        expected = (
            self.budget_fit + self.need_fit + self.timeline_fit
            + self.decision_intent + self.project_clarity + self.company_fit
        )
        if self.total != expected:
            raise ValueError("total must equal sum of score components")
        return self


class QualificationResult(BaseModel):
    score: ScoreBreakdown
    fit: Fit
    priority: Priority
    estimated_deal_min_usd: int | None
    estimated_deal_max_usd: int | None
    missing_information: list[str]
    recommended_action: RecommendedAction
    reason_summary: list[str]


class Lead(BaseModel):
    id: UUID
    raw_text: str
    source: Literal["website"] = "website"
    created_at: datetime
    status: LeadStatus


class Draft(BaseModel):
    id: UUID
    lead_id: UUID
    body: str = Field(min_length=1)
    status: DraftStatus
    created_at: datetime
    reviewed_at: datetime | None = None


class Event(BaseModel):
    id: UUID
    lead_id: UUID
    event_type: str
    payload_json: str | None
    created_at: datetime
