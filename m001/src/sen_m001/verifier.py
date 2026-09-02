"""Independent verification of the durable M001-B001 evidence chain."""

from __future__ import annotations

import json
from typing import Any

from .canonical import hash_object, sha256_hex
from .cas import ContentAddressedStore
from .database import Database


_PRE_APPROVAL_EVIDENCE = {
    "LEAD_RECEIVED",
    "LEAD_NORMALIZED",
    "LEAD_EXTRACTED",
    "LEAD_QUALIFIED",
    "APPROVAL_REQUESTED",
}
_COMMIT_EVIDENCE = {
    "HUMAN_APPROVAL_RECORDED",
    "DESTINATION_COMMITTED",
    "BUNDLE_MATERIALIZED",
}
_FINAL_EVIDENCE = {"ARTIFACT_HASH_VERIFIED", "PROVENANCE_CHAIN_VERIFIED"}


class Verifier:
    """Recompute truth from stored bytes and records instead of trusting state."""

    def __init__(self, database: Database, cas: ContentAddressedStore):
        self.database = database
        self.cas = cas

    def verify(self, run_id: str) -> dict[str, Any]:
        run = self.database.get_run(run_id)
        if run is None:
            return {
                "valid": False,
                "state": "MISSING",
                "bundle_sha256": None,
                "checks": {"RUN_EXISTS": False},
            }

        document_types = (
            "inbound_lead_v1",
            "normalized_lead_v1",
            "extracted_lead_v1",
            "lead_decision_candidate_v1",
        )
        documents = {
            document_type: self.database.get_document(run_id, document_type)
            for document_type in document_types
        }
        approval = self.database.get_approval(run_id)
        crm_record = self.database.get_crm_record(run_id)
        artifact = self.database.get_artifact(run_id)
        evidence = set(self.database.evidence_types(run_id))

        documents_exist = all(document is not None for document in documents.values())
        document_hashes_match = documents_exist and all(
            hash_object(document["content"]) == document["content_sha256"]
            for document in documents.values()
            if document is not None
        )
        candidate_document = documents["lead_decision_candidate_v1"]
        candidate = candidate_document["content"] if candidate_document else None
        candidate_self_hash_match = False
        if candidate is not None and "candidate_sha256" in candidate:
            candidate_body = dict(candidate)
            candidate_sha256 = candidate_body.pop("candidate_sha256")
            candidate_self_hash_match = hash_object(candidate_body) == candidate_sha256

        approval_binding = bool(
            candidate
            and approval
            and approval["decision"] == "APPROVE"
            and approval["candidate_sha256"] == candidate["candidate_sha256"]
            and run["candidate_sha256"] == candidate["candidate_sha256"]
        )
        destination_binding = bool(
            approval
            and crm_record
            and self.database.count_crm_rows(run_id) == 1
            and crm_record["approval_id"] == approval["approval_id"]
        )
        artifact_binding = bool(
            approval
            and artifact
            and self.database.count_artifacts(run_id) == 1
            and artifact["artifact_kind"] == "lead_decision_bundle_v1"
            and artifact["approval_id"] == approval["approval_id"]
        )

        bundle_bytes: bytes | None = None
        cas_hash_match = False
        cas_ref_match = False
        bundle: dict[str, Any] | None = None
        if artifact is not None:
            try:
                cas_ref_match = (
                    self.cas.ref_for_hash(artifact["content_sha256"])
                    == artifact["cas_ref"]
                )
                bundle_bytes = self.cas.resolve_ref(artifact["cas_ref"]).read_bytes()
                cas_hash_match = (
                    sha256_hex(bundle_bytes) == artifact["content_sha256"]
                )
                bundle = json.loads(bundle_bytes)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                bundle = None

        bundle_binding = bool(
            bundle
            and candidate
            and approval
            and crm_record
            and bundle.get("artifact_kind") == "lead_decision_bundle_v1"
            and bundle.get("run_id") == run_id
            and bundle.get("candidate_sha256") == candidate["candidate_sha256"]
            and bundle.get("candidate") == candidate
            and bundle.get("approval") == approval
            and bundle.get("destination", {}).get("crm_record_id")
            == crm_record["crm_record_id"]
            and bundle.get("provenance", {}).get("candidate_document_sha256")
            == candidate_document["content_sha256"]
            and bundle.get("provenance", {}).get("approval_sha256")
            == hash_object(approval)
            and bundle.get("provenance", {}).get("crm_record_sha256")
            == hash_object(crm_record)
        )
        required_evidence = _PRE_APPROVAL_EVIDENCE | _COMMIT_EVIDENCE
        if run["state"] == "COMPLETED":
            required_evidence |= _FINAL_EVIDENCE

        checks = {
            "RUN_STATE_ALLOWED": run["state"] in {"BUNDLE_MATERIALIZED", "COMPLETED"},
            "DOCUMENTS_EXIST": documents_exist,
            "DOCUMENT_HASHES_MATCH": document_hashes_match,
            "CANDIDATE_SELF_HASH_MATCH": candidate_self_hash_match,
            "APPROVAL_HASH_MATCH": approval_binding,
            "DESTINATION_UNIQUE_AND_BOUND": destination_binding,
            "ARTIFACT_BOUND": artifact_binding,
            "CAS_REF_MATCH": cas_ref_match,
            "CAS_HASH_MATCH": cas_hash_match,
            "BUNDLE_PROVENANCE_MATCH": bundle_binding,
            "REQUIRED_EVIDENCE_PRESENT": required_evidence.issubset(evidence),
        }
        return {
            "valid": all(checks.values()),
            "state": run["state"],
            "bundle_sha256": artifact["content_sha256"] if artifact else None,
            "checks": checks,
        }
