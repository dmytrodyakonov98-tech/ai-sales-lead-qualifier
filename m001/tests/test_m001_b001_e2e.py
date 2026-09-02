import tempfile
import unittest
from pathlib import Path

from sen_m001.cas import ContentAddressedStore
from sen_m001.database import Database
from sen_m001.service import ApprovalMismatch, LeadQualifierService
from sen_m001.verifier import Verifier
from tests.test_domain import FIXED_FORM


class M001B001Proof(unittest.TestCase):
    def test_all_nine_frozen_proof_gates(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = root / "factory.db"
            cas_root = root / "cas"
            database = Database(database_path)
            database.initialize()
            cas = ContentAddressedStore(cas_root)
            service = LeadQualifierService(database, cas)

            pending = service.submit_form(FIXED_FORM)
            self.assertEqual("AWAITING_HUMAN_APPROVAL", pending["state"])
            self.assertEqual(0, database.count_crm_rows(pending["run_id"]))
            self.assertEqual(0, database.count_artifacts(pending["run_id"]))

            with self.assertRaises(ApprovalMismatch):
                service.approve(pending["run_id"], "f" * 64)
            self.assertEqual(0, database.count_crm_rows(pending["run_id"]))

            completed = service.approve(
                pending["run_id"], pending["candidate_sha256"]
            )
            repeated = service.approve(
                pending["run_id"], pending["candidate_sha256"]
            )
            self.assertEqual(1, database.count_crm_rows(pending["run_id"]))
            self.assertEqual(
                completed["crm_record_id"], repeated["crm_record_id"]
            )
            self.assertEqual(
                completed["bundle_sha256"], repeated["bundle_sha256"]
            )
            self.assertEqual(
                completed["bundle_sha256"],
                database.get_artifact(pending["run_id"])["content_sha256"],
            )

            original_ids = {
                "approval_id": completed["approval_id"],
                "crm_record_id": completed["crm_record_id"],
                "bundle_sha256": completed["bundle_sha256"],
            }
            database.close()
            reopened = Database(database_path)
            reopened.initialize()
            proof = Verifier(reopened, ContentAddressedStore(cas_root)).verify(
                pending["run_id"]
            )
            self.assertTrue(proof["valid"])
            self.assertEqual("COMPLETED", proof["state"])
            self.assertEqual(
                original_ids["approval_id"],
                reopened.get_approval(pending["run_id"])["approval_id"],
            )
            self.assertEqual(
                original_ids["crm_record_id"],
                reopened.get_crm_record(pending["run_id"])["crm_record_id"],
            )
            self.assertEqual(
                original_ids["bundle_sha256"], proof["bundle_sha256"]
            )

            artifact = reopened.get_artifact(pending["run_id"])
            object_path = ContentAddressedStore(cas_root).resolve_ref(
                artifact["cas_ref"]
            )
            object_path.write_bytes(object_path.read_bytes() + b"x")
            tampered = Verifier(reopened, ContentAddressedStore(cas_root)).verify(
                pending["run_id"]
            )
            self.assertFalse(tampered["valid"])
            self.assertFalse(tampered["checks"]["CAS_HASH_MATCH"])
            reopened.close()


if __name__ == "__main__":
    unittest.main()
