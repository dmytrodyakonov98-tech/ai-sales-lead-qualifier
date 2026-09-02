"""State-guarded application service for the deterministic B001 vertical."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from hmac import compare_digest
from typing import Any
from uuid import uuid4

from .canonical import canonical_bytes, hash_object
from .cas import ContentAddressedStore
from .database import Database
from .domain import EXPECTED_FIELDS, build_candidate, normalize_form


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def _document(
    run_id: str, document_type: str, content: Mapping[str, Any], created_at: str
) -> dict[str, Any]:
    body = dict(content)
    return {
        "document_id": _id("doc"),
        "run_id": run_id,
        "document_type": document_type,
        "revision": 1,
        "content": body,
        "content_sha256": hash_object(body),
        "created_at": created_at,
    }


def _evidence(
    run_id: str,
    evidence_type: str,
    subject_id: str,
    input_hashes: list[str],
    output_hashes: list[str],
    created_at: str,
) -> dict[str, Any]:
    return {
        "evidence_id": _id("evidence"),
        "run_id": run_id,
        "evidence_type": evidence_type,
        "subject_id": subject_id,
        "input_hashes": input_hashes,
        "output_hashes": output_hashes,
        "metadata": {"producer": "DETERMINISTIC_KERNEL"},
        "created_at": created_at,
    }


def _event(
    run_id: str,
    event_type: str,
    subject_id: str,
    payload: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    return {
        "event_id": _id("event"),
        "run_id": run_id,
        "event_type": event_type,
        "actor_type": "KERNEL",
        "actor_id": None,
        "subject_id": subject_id,
        "payload": dict(payload),
        "created_at": created_at,
    }


class LeadQualifierService:
    """Own the B001 state transitions and authority boundary."""

    def __init__(
        self, database: Database, cas: ContentAddressedStore | None = None
    ):
        self.database = database
        self.cas = cas

    def submit_form(self, form: Mapping[str, str]) -> dict[str, Any]:
        run_id = _id("run")
        created_at = _now()
        raw = {field: form[field] for field in EXPECTED_FIELDS if field in form}
        normalized = normalize_form(form)
        candidate = build_candidate(normalized)
        extracted = candidate["extracted_lead"]

        raw_document = _document(run_id, "inbound_lead_v1", raw, created_at)
        normalized_document = _document(
            run_id, "normalized_lead_v1", normalized, created_at
        )
        extracted_document = _document(
            run_id, "extracted_lead_v1", extracted, created_at
        )
        candidate_document = _document(
            run_id, "lead_decision_candidate_v1", candidate, created_at
        )
        run = {
            "run_id": run_id,
            "state": "AWAITING_HUMAN_APPROVAL",
            "candidate_sha256": candidate["candidate_sha256"],
            "created_at": created_at,
            "updated_at": created_at,
        }

        evidence_rows = (
            _evidence(
                run_id,
                "LEAD_RECEIVED",
                raw_document["document_id"],
                [],
                [raw_document["content_sha256"]],
                created_at,
            ),
            _evidence(
                run_id,
                "LEAD_NORMALIZED",
                normalized_document["document_id"],
                [raw_document["content_sha256"]],
                [normalized_document["content_sha256"]],
                created_at,
            ),
            _evidence(
                run_id,
                "LEAD_EXTRACTED",
                extracted_document["document_id"],
                [normalized_document["content_sha256"]],
                [extracted_document["content_sha256"]],
                created_at,
            ),
            _evidence(
                run_id,
                "LEAD_QUALIFIED",
                candidate_document["document_id"],
                [extracted_document["content_sha256"]],
                [candidate["candidate_sha256"]],
                created_at,
            ),
            _evidence(
                run_id,
                "APPROVAL_REQUESTED",
                candidate_document["document_id"],
                [candidate["candidate_sha256"]],
                [],
                created_at,
            ),
        )

        with self.database.transaction() as connection:
            self.database.insert_run(connection, run)
            for document in (
                raw_document,
                normalized_document,
                extracted_document,
                candidate_document,
            ):
                self.database.insert_document(connection, document)
            for evidence in evidence_rows:
                self.database.append_evidence(connection, evidence)
            for state in (
                "RECEIVED",
                "NORMALIZED",
                "EXTRACTED",
                "QUALIFIED",
                "AWAITING_HUMAN_APPROVAL",
            ):
                self.database.append_event(
                    connection,
                    _event(
                        run_id,
                        "RUN_STATE_CHANGED",
                        run_id,
                        {"to": state},
                        created_at,
                    ),
                )

        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        candidate_document = self.database.get_document(
            run_id, "lead_decision_candidate_v1"
        )
        if candidate_document is None:
            raise RuntimeError("candidate document is missing")
        candidate = candidate_document["content"]
        return {
            "run_id": run_id,
            "state": run["state"],
            "candidate_sha256": run["candidate_sha256"],
            "score": candidate["qualification"]["score"],
            "decision": candidate["qualification"]["decision"],
            "next_action": candidate["qualification"]["next_action"],
            "response_draft": candidate["response_draft"],
        }

    def approve(
        self,
        run_id: str,
        candidate_sha256: str,
        actor_id: str = "LOCAL_OWNER",
    ) -> dict[str, Any]:
        if self.cas is None:
            raise RuntimeError("CAS is required for approval")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        stored_hash = str(run["candidate_sha256"])
        if not compare_digest(stored_hash, candidate_sha256):
            raise ApprovalMismatch("approval does not match the exact candidate hash")
        if run["state"] == "COMPLETED":
            return self._committed_result(run_id)
        if run["state"] != "AWAITING_HUMAN_APPROVAL":
            raise InvalidRunState(str(run["state"]))

        candidate_document = self.database.get_document(
            run_id, "lead_decision_candidate_v1"
        )
        if candidate_document is None:
            raise RuntimeError("candidate document is missing")
        candidate = candidate_document["content"]
        candidate_body = dict(candidate)
        embedded_hash = candidate_body.pop("candidate_sha256", None)
        current_hash = hash_object(candidate_body)
        current_document_hash = hash_object(candidate)
        if not (
            isinstance(embedded_hash, str)
            and compare_digest(embedded_hash, current_hash)
            and compare_digest(stored_hash, current_hash)
            and compare_digest(
                str(candidate_document["content_sha256"]), current_document_hash
            )
        ):
            raise ApprovalMismatch(
                "current canonical candidate does not match the reviewed version"
            )
        decided_at = _now()
        approval = {
            "approval_id": _id("approval"),
            "run_id": run_id,
            "candidate_sha256": stored_hash,
            "actor_id": actor_id,
            "decision": "APPROVE",
            "decided_at": decided_at,
        }
        crm_record = {
            "crm_record_id": _id("crm"),
            "run_id": run_id,
            "approval_id": approval["approval_id"],
            "lead": {
                "extracted_lead": candidate["extracted_lead"],
                "qualification": candidate["qualification"],
                "response_draft": candidate["response_draft"],
            },
            "created_at": decided_at,
        }
        bundle = {
            "schema_version": "1",
            "artifact_kind": "lead_decision_bundle_v1",
            "run_id": run_id,
            "candidate_sha256": stored_hash,
            "candidate": candidate,
            "approval": approval,
            "destination": {
                "destination_kind": "built_in_crm_inbox",
                "crm_record_id": crm_record["crm_record_id"],
                "created_at": decided_at,
            },
            "provenance": {
                "candidate_document_sha256": candidate_document["content_sha256"],
                "approval_sha256": hash_object(approval),
                "crm_record_sha256": hash_object(crm_record),
            },
        }
        bundle_sha256, cas_ref = self.cas.put(canonical_bytes(bundle))
        artifact = {
            "artifact_id": _id("artifact"),
            "run_id": run_id,
            "artifact_kind": "lead_decision_bundle_v1",
            "content_sha256": bundle_sha256,
            "cas_ref": cas_ref,
            "approval_id": approval["approval_id"],
            "created_at": decided_at,
        }

        with self.database.transaction() as connection:
            self.database.insert_approval(connection, approval)
            self.database.insert_crm_record(connection, crm_record)
            self.database.insert_artifact(connection, artifact)
            for evidence in (
                _evidence(
                    run_id,
                    "HUMAN_APPROVAL_RECORDED",
                    approval["approval_id"],
                    [stored_hash],
                    [hash_object(approval)],
                    decided_at,
                ),
                _evidence(
                    run_id,
                    "DESTINATION_COMMITTED",
                    crm_record["crm_record_id"],
                    [stored_hash, hash_object(approval)],
                    [hash_object(crm_record)],
                    decided_at,
                ),
                _evidence(
                    run_id,
                    "BUNDLE_MATERIALIZED",
                    artifact["artifact_id"],
                    [stored_hash, hash_object(approval), hash_object(crm_record)],
                    [bundle_sha256],
                    decided_at,
                ),
            ):
                self.database.append_evidence(connection, evidence)
            for state in (
                "APPROVED",
                "DESTINATION_COMMITTED",
                "BUNDLE_MATERIALIZED",
            ):
                self.database.append_event(
                    connection,
                    _event(
                        run_id,
                        "RUN_STATE_CHANGED",
                        run_id,
                        {"to": state},
                        decided_at,
                    ),
                )
            self.database.update_run_state(
                connection, run_id, "BUNDLE_MATERIALIZED", decided_at
            )

        from .verifier import Verifier

        proof = Verifier(self.database, self.cas).verify(run_id)
        if not proof["valid"]:
            raise RuntimeError(f"durable bundle verification failed: {proof['checks']}")

        verified_at = _now()
        with self.database.transaction() as connection:
            for evidence in (
                _evidence(
                    run_id,
                    "ARTIFACT_HASH_VERIFIED",
                    artifact["artifact_id"],
                    [bundle_sha256],
                    [bundle_sha256],
                    verified_at,
                ),
                _evidence(
                    run_id,
                    "PROVENANCE_CHAIN_VERIFIED",
                    artifact["artifact_id"],
                    [stored_hash, bundle_sha256],
                    [bundle_sha256],
                    verified_at,
                ),
            ):
                self.database.append_evidence(connection, evidence)
            for state in ("VERIFIED", "COMPLETED"):
                self.database.append_event(
                    connection,
                    _event(
                        run_id,
                        "RUN_STATE_CHANGED",
                        run_id,
                        {"to": state},
                        verified_at,
                    ),
                )
            self.database.update_run_state(
                connection, run_id, "COMPLETED", verified_at
            )
        return self._committed_result(run_id)

    def _committed_result(self, run_id: str) -> dict[str, Any]:
        run = self.database.get_run(run_id)
        approval = self.database.get_approval(run_id)
        crm_record = self.database.get_crm_record(run_id)
        artifact = self.database.get_artifact(run_id)
        if run is None or approval is None or crm_record is None or artifact is None:
            raise RuntimeError("committed run is incomplete")
        from .verifier import Verifier

        proof = Verifier(self.database, self.cas).verify(run_id)  # type: ignore[arg-type]
        return {
            "run_id": run_id,
            "state": run["state"],
            "approval_id": approval["approval_id"],
            "crm_record_id": crm_record["crm_record_id"],
            "bundle_sha256": artifact["content_sha256"],
            "cas_ref": artifact["cas_ref"],
            "verified": proof["valid"],
        }


class ApprovalMismatch(PermissionError):
    """The human decision did not bind the currently stored candidate."""


class InvalidRunState(RuntimeError):
    """The requested transition is not allowed from the current state."""
