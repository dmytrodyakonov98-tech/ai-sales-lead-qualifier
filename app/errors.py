class AppError(Exception):
    code = "APP_ERROR"


class LLMExtractionError(AppError):
    code = "LLM_EXTRACTION_FAILED"


class LLMDraftingError(AppError):
    code = "LLM_DRAFT_FAILED"


class NotFoundError(AppError):
    code = "NOT_FOUND"


class LifecycleConflictError(AppError):
    code = "LIFECYCLE_CONFLICT"
