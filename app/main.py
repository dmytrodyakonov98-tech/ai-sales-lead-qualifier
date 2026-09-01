from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_health import router as health_router
from app.api.routes_leads import router as leads_router
from app.config import Settings
from app.llm.client import OpenAILLMClient, UnavailableLLMClient
from app.services.extractor import LeadExtractor
from app.services.lead_pipeline import LeadPipeline
from app.services.response_drafter import ResponseDrafter
from app.storage.database import sqlite_path_from_url
from app.storage.repositories import SQLiteLeadStore

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _build_runtime_services(settings: Settings) -> dict[str, object]:
    store = SQLiteLeadStore(sqlite_path_from_url(settings.database_url))
    store.initialize()
    if settings.llm_provider == "openai" and settings.openai_api_key:
        llm = OpenAILLMClient(api_key=settings.openai_api_key, model=settings.llm_model)
    else:
        llm = UnavailableLLMClient()
    pipeline = LeadPipeline(
        store=store,
        extractor=LeadExtractor(llm),
        drafter=ResponseDrafter(llm),
    )
    return {"store": store, "pipeline": pipeline}


def attach_frontend(application: FastAPI) -> None:
    application.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @application.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(FRONTEND_DIR / "index.html")


def create_app(*, settings: Settings | None = None, services: dict[str, object] | None = None) -> FastAPI:
    settings = settings or Settings()
    application = FastAPI(title="AI Sales Lead Qualifier", version="0.1.0")
    application.state.settings = settings
    application.state.services = services if services is not None else _build_runtime_services(settings)
    application.include_router(health_router)
    application.include_router(leads_router)
    attach_frontend(application)
    return application


app = create_app()
