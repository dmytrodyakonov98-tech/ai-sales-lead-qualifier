def test_post_lead_trims_input_and_returns_201(client) -> None:
    response = client.post("/api/leads", json={"raw_text": "   We need an AI support agent with a $10k budget.   "})
    assert response.status_code == 201
    body = response.json()
    assert body["lead"]["status"] == "needs_review"
    assert body["qualification"]["score"]["total"] >= 70
    assert body["draft"]["status"] == "pending"


def test_post_lead_rejects_too_short_text(client) -> None:
    response = client.post("/api/leads", json={"raw_text": "short"})
    assert response.status_code == 422


def test_extraction_failure_returns_controlled_502(failing_client) -> None:
    response = failing_client.post("/api/leads", json={"raw_text": "A sufficiently long inbound sales lead."})
    assert response.status_code == 502
    assert response.json() == {
        "error": {"code": "LLM_EXTRACTION_FAILED", "message": "Lead extraction could not be completed."}
    }
    assert "traceback" not in response.text.lower()
    assert "api_key" not in response.text.lower()


def _create_lead_id(client) -> str:
    created = client.post(
        "/api/leads",
        json={"raw_text": "We need an AI support agent with a $10k budget."},
    )
    assert created.status_code == 201
    return created.json()["lead"]["id"]


def test_approve_pending_draft(client) -> None:
    lead_id = _create_lead_id(client)
    response = client.post(f"/api/leads/{lead_id}/draft/approve")
    assert response.status_code == 200
    assert response.json()["lead"]["status"] == "approved"
    assert response.json()["draft"]["status"] == "approved"


def test_reject_pending_draft(client) -> None:
    lead_id = _create_lead_id(client)
    response = client.post(f"/api/leads/{lead_id}/draft/reject")
    assert response.status_code == 200
    assert response.json()["lead"]["status"] == "rejected"
    assert response.json()["draft"]["status"] == "rejected"


def test_double_approval_returns_409(client) -> None:
    lead_id = _create_lead_id(client)
    assert client.post(f"/api/leads/{lead_id}/draft/approve").status_code == 200
    conflict = client.post(f"/api/leads/{lead_id}/draft/approve")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "LIFECYCLE_CONFLICT"


def test_approve_after_reject_returns_409(client) -> None:
    lead_id = _create_lead_id(client)
    assert client.post(f"/api/leads/{lead_id}/draft/reject").status_code == 200
    assert client.post(f"/api/leads/{lead_id}/draft/approve").status_code == 409


from fastapi.testclient import TestClient

from app.main import create_app
from app.storage.repositories import SQLiteLeadStore
from tests.fixtures.fake_llm import FakeLLMClient, GOOD_EXTRACTION


def test_incomplete_lead_requests_more_information(client_factory) -> None:
    extraction = {
        **GOOD_EXTRACTION,
        "company_name": None,
        "company_size": None,
        "current_stack": None,
        "budget_min_usd": None,
        "budget_max_usd": None,
        "timeline_days": None,
        "decision_intent": "unknown",
        "project_clarity": "low",
    }
    client = client_factory(FakeLLMClient(extraction=extraction, draft={"body": "Could you share your budget, timeline, and current support stack?"}))
    response = client.post("/api/leads", json={"raw_text": "We want an AI support workflow but are still defining the project."})

    assert response.status_code == 201
    body = response.json()
    assert body["qualification"]["recommended_action"] == "request_more_information"
    assert set(body["qualification"]["missing_information"]) >= {"company_name", "budget", "timeline", "current_stack"}
    assert body["draft"]["status"] == "pending"


def test_unrelated_lead_is_deprioritized(client_factory) -> None:
    extraction = {
        **GOOD_EXTRACTION,
        "company_name": "Tiny Shop",
        "company_size": 2,
        "need": "Logo design for a local bakery",
        "need_category": "unrelated_or_unknown",
        "budget_min_usd": 100,
        "budget_max_usd": 500,
        "timeline_days": 120,
        "decision_intent": "low",
        "project_clarity": "low",
    }
    client = client_factory(FakeLLMClient(extraction=extraction, draft={"body": "Thanks for the inquiry."}))
    response = client.post("/api/leads", json={"raw_text": "We need a bakery logo and have a very small budget."})

    assert response.status_code == 201
    body = response.json()
    assert body["qualification"]["fit"] == "weak"
    assert body["qualification"]["priority"] == "low"
    assert body["qualification"]["recommended_action"] == "deprioritize"


def test_malformed_llm_extraction_returns_502_and_failed_event(client_factory) -> None:
    client = client_factory(FakeLLMClient(extraction={"need": ""}))
    response = client.post("/api/leads", json={"raw_text": "This is a valid inbound lead body for a failure-path test."})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LLM_EXTRACTION_FAILED"

    store = client.app.state.services["store"]
    summary = store.list_lead_summaries()[0]
    assert summary.lead.status.value == "failed"
    assert store.list_events(summary.lead.id)[-1].event_type == "pipeline_failed"
    assert store.get_draft(summary.lead.id) is None


def test_list_and_get_survive_store_reopen(client) -> None:
    created = client.post(
        "/api/leads",
        json={"raw_text": "We need an AI support agent with a $10k budget in four weeks."},
    )
    assert created.status_code == 201
    lead_id = created.json()["lead"]["id"]

    original_store = client.app.state.services["store"]
    reopened = SQLiteLeadStore(original_store.path)
    reopened.initialize()
    restarted_client = TestClient(create_app(services={"store": reopened, "pipeline": object()}))

    listed = restarted_client.get("/api/leads")
    fetched = restarted_client.get(f"/api/leads/{lead_id}")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == lead_id
    assert fetched.status_code == 200
    assert fetched.json()["lead"]["id"] == lead_id
    assert fetched.json()["draft"]["status"] == "pending"


def test_public_error_codes_are_stable(client, failing_client) -> None:
    unknown = client.get("/api/leads/00000000-0000-0000-0000-000000000001")
    transport_validation = client.post("/api/leads", json={"raw_text": "short"})
    llm_failure = failing_client.post("/api/leads", json={"raw_text": "A sufficiently long inbound lead body."})

    created = client.post("/api/leads", json={"raw_text": "We need an AI support agent with a $10k budget."}).json()
    lead_id = created["lead"]["id"]
    assert client.post(f"/api/leads/{lead_id}/draft/approve").status_code == 200
    conflict = client.post(f"/api/leads/{lead_id}/draft/reject")

    assert unknown.status_code == 404
    assert conflict.status_code == 409
    assert llm_failure.status_code == 502
    assert transport_validation.status_code == 422
    assert "traceback" not in llm_failure.text.lower()
    assert "api_key" not in llm_failure.text.lower()
