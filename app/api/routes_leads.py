from uuid import UUID

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.errors import LifecycleConflictError, LLMDraftingError, LLMExtractionError, NotFoundError
from app.models.api import LeadCreateRequest, LeadDetailResponse, LeadSummaryResponse
from app.services.review import ReviewService

router = APIRouter(prefix="/api/leads", tags=["leads"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def _detail_response(record) -> LeadDetailResponse:
    return LeadDetailResponse(
        lead=record.lead,
        facts=record.facts,
        qualification=record.qualification,
        draft=record.draft,
    )


@router.post("", response_model=LeadDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(payload: LeadCreateRequest, request: Request):
    pipeline = request.app.state.services["pipeline"]
    try:
        record = await pipeline.process(payload.raw_text)
        return _detail_response(record)
    except LLMExtractionError:
        return _error(502, "LLM_EXTRACTION_FAILED", "Lead extraction could not be completed.")
    except LLMDraftingError:
        return _error(502, "LLM_DRAFT_FAILED", "Lead response draft could not be completed.")
    except Exception:
        return _error(500, "INTERNAL_ERROR", "The lead could not be processed.")


@router.get("", response_model=list[LeadSummaryResponse])
def list_leads(request: Request):
    store = request.app.state.services["store"]
    return [
        LeadSummaryResponse(
            id=item.lead.id,
            created_at=item.lead.created_at,
            company_name=item.company_name,
            score=item.score,
            priority=item.priority,
            status=item.lead.status.value,
        )
        for item in store.list_lead_summaries()
    ]


@router.get("/{lead_id}", response_model=LeadDetailResponse)
def get_lead(lead_id: UUID, request: Request):
    store = request.app.state.services["store"]
    record = store.get_lead_detail(lead_id)
    if record is None:
        return _error(404, "LEAD_NOT_FOUND", "Lead was not found.")
    return _detail_response(record)


def _review_response(lead_id: UUID, request: Request, *, approve: bool):
    service = ReviewService(request.app.state.services["store"])
    try:
        record = service.approve(lead_id) if approve else service.reject(lead_id)
        return _detail_response(record)
    except NotFoundError:
        return _error(404, "LEAD_NOT_FOUND", "Lead or draft was not found.")
    except LifecycleConflictError:
        return _error(409, "LIFECYCLE_CONFLICT", "Draft has already been reviewed.")


@router.post("/{lead_id}/draft/approve", response_model=LeadDetailResponse)
def approve_draft(lead_id: UUID, request: Request):
    return _review_response(lead_id, request, approve=True)


@router.post("/{lead_id}/draft/reject", response_model=LeadDetailResponse)
def reject_draft(lead_id: UUID, request: Request):
    return _review_response(lead_id, request, approve=False)
