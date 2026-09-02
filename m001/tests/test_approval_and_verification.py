import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from sen_m001.canonical import canonical_bytes, hash_object
from sen_m001.cas import ContentAddressedStore
from sen_m001.database import Database
from sen_m001.service import ApprovalMismatch, LeadQualifierService
from sen_m001.verifier import Verifier
from tests.test_domain import FIXED_FORM


class ApprovalAndVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.database_path = root / "factory.db"
        self.cas_root = root / "cas"
        self.database = Database(self.database_path)
        self.database.initialize()
        self.cas = ContentAddressedStore(self.cas_root)
        self.service = LeadQualifierService(self.database, self.cas)

    def tearDown(self):
        self.database.close()
        self.temporary_directory.cleanup()

    def test_wrong_hash_cannot_create_destination_approval_or_artifact(self):
        pending = self.service.submit_form(FIXED_FORM)

        with self.assertRaises(ApprovalMismatch):
            self.service.approve(pending["run_id"], "0" * 64)

        self.assertEqual(0, self.database.count_approvals(pending["run_id"]))
        self.assertEqual(0, self.database.count_crm_rows(pending["run_id"]))
        self.assertEqual(0, self.database.count_artifacts(pending["run_id"]))
        self.assertEqual(
            "AWAITING_HUMAN_APPROVAL",
            self.database.get_run(pending["run_id"])["state"],
        )

    def test_stale_approval_fails_closed_before_swapped_draft_side_effects(self):
        original = "ORIGINAL DRAFT — human reviewed this exact text."
        swapped = "SWAPPED DRAFT — different content inserted after human review."
        self.assertEqual(
            "a77f409eb96bce59901f31e99f900bb7851e250f366e353bba7568c76c834f19",
            hashlib.sha256(original.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            "34e1adb151d169ec868757fce478907e5687c0afaa9bb07ac053afdc60977e84",
            hashlib.sha256(swapped.encode("utf-8")).hexdigest(),
        )
        pending = self.service.submit_form(FIXED_FORM)
        candidate_document = self.database.get_document(
            pending["run_id"], "lead_decision_candidate_v1"
        )
        swapped_candidate = candidate_document["content"]
        swapped_candidate["response_draft"] = swapped
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE documents SET content_json = ?, content_sha256 = ? "
                "WHERE document_id = ?",
                (
                    canonical_bytes(swapped_candidate).decode("utf-8"),
                    hash_object(swapped_candidate),
                    candidate_document["document_id"],
                ),
            )

        caught_error = None
        try:
            self.service.approve(pending["run_id"], pending["candidate_sha256"])
        except Exception as error:  # Regression must also inspect committed side effects.
            caught_error = error

        self.assertEqual(0, self.database.count_approvals(pending["run_id"]))
        self.assertEqual(0, self.database.count_crm_rows(pending["run_id"]))
        self.assertEqual(0, self.database.count_artifacts(pending["run_id"]))
        self.assertEqual(
            "AWAITING_HUMAN_APPROVAL",
            self.database.get_run(pending["run_id"])["state"],
        )
        self.assertIsInstance(caught_error, ApprovalMismatch)

    def test_exact_approval_commits_once_and_verifies_after_restart(self):
        pending = self.service.submit_form(FIXED_FORM)

        first = self.service.approve(
            pending["run_id"], pending["candidate_sha256"]
        )
        second = self.service.approve(
            pending["run_id"], pending["candidate_sha256"]
        )

        self.assertEqual("COMPLETED", first["state"])
        self.assertTrue(first["verified"])
        self.assertEqual(first["approval_id"], second["approval_id"])
        self.assertEqual(first["crm_record_id"], second["crm_record_id"])
        self.assertEqual(first["bundle_sha256"], second["bundle_sha256"])
        self.assertEqual(1, self.database.count_approvals(pending["run_id"]))
        self.assertEqual(1, self.database.count_crm_rows(pending["run_id"]))
        self.assertEqual(1, self.database.count_artifacts(pending["run_id"]))

        bundle = json.loads(self.cas.get(first["bundle_sha256"]))
        self.assertEqual("lead_decision_bundle_v1", bundle["artifact_kind"])
        self.assertEqual(pending["candidate_sha256"], bundle["candidate_sha256"])
        self.assertEqual(first["approval_id"], bundle["approval"]["approval_id"])
        self.assertEqual(first["crm_record_id"], bundle["destination"]["crm_record_id"])

        self.database.close()
        reopened = Database(self.database_path)
        reopened.initialize()
        proof = Verifier(reopened, ContentAddressedStore(self.cas_root)).verify(
            pending["run_id"]
        )

        self.assertTrue(proof["valid"])
        self.assertEqual("COMPLETED", proof["state"])
        self.assertTrue(all(proof["checks"].values()))
        reopened.close()

    def test_bundle_tampering_is_detected_even_when_stored_state_says_completed(self):
        pending = self.service.submit_form(FIXED_FORM)
        completed = self.service.approve(
            pending["run_id"], pending["candidate_sha256"]
        )
        object_path = self.cas.resolve_ref(completed["cas_ref"])
        object_path.write_bytes(object_path.read_bytes() + b"tampered")

        proof = Verifier(self.database, self.cas).verify(pending["run_id"])

        self.assertFalse(proof["valid"])
        self.assertFalse(proof["checks"]["CAS_HASH_MATCH"])
        self.assertEqual("COMPLETED", self.database.get_run(pending["run_id"])["state"])


if __name__ == "__main__":
    unittest.main()
