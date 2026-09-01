from pydantic import BaseModel

from app.models.domain import Draft, ExtractedLeadFacts, Lead, QualificationResult


class LeadDetailRecord(BaseModel):
    lead: Lead
    facts: ExtractedLeadFacts | None = None
    qualification: QualificationResult | None = None
    draft: Draft | None = None


class LeadSummaryRecord(BaseModel):
    lead: Lead
    company_name: str | None = None
    score: int | None = None
    priority: str | None = None
