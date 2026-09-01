from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.domain import Draft, ExtractedLeadFacts, Lead, QualificationResult


class LeadCreateRequest(BaseModel):
    raw_text: str = Field(min_length=10, max_length=10_000)

    @field_validator("raw_text", mode="before")
    @classmethod
    def trim_raw_text(cls, value: str) -> str:
        return value.strip()


class LeadDetailResponse(BaseModel):
    lead: Lead
    facts: ExtractedLeadFacts | None = None
    qualification: QualificationResult | None = None
    draft: Draft | None = None


class LeadSummaryResponse(BaseModel):
    id: UUID
    created_at: datetime
    company_name: str | None
    score: int | None
    priority: str | None
    status: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody
