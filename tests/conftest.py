from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.extractor import LeadExtractor
from app.services.lead_pipeline import LeadPipeline
from app.services.response_drafter import ResponseDrafter
from app.storage.repositories import SQLiteLeadStore
from tests.fixtures.fake_llm import FakeLLMClient, GOOD_EXTRACTION


def make_client(tmp_path, fake: FakeLLMClient) -> TestClient:
    store = SQLiteLeadStore(tmp_path / "leads.db")
    store.initialize()
    pipeline = LeadPipeline(
        store=store,
        extractor=LeadExtractor(fake),
        drafter=ResponseDrafter(fake),
    )
    return TestClient(create_app(services={"store": store, "pipeline": pipeline}))


@pytest.fixture
def client(tmp_path) -> TestClient:
    fake = FakeLLMClient(
        extraction=GOOD_EXTRACTION,
        draft={"body": "Thanks for reaching out. Let's schedule a discovery call."},
    )
    return make_client(tmp_path, fake)


@pytest.fixture
def failing_client(tmp_path) -> TestClient:
    return make_client(tmp_path, FakeLLMClient(extraction_error=ValueError("provider payload")))


@pytest.fixture
def client_factory(tmp_path):
    def build(fake: FakeLLMClient) -> TestClient:
        store = SQLiteLeadStore(tmp_path / f"{uuid4()}.db")
        store.initialize()
        pipeline = LeadPipeline(
            store=store,
            extractor=LeadExtractor(fake),
            drafter=ResponseDrafter(fake),
        )
        return TestClient(create_app(services={"store": store, "pipeline": pipeline}))
    return build
