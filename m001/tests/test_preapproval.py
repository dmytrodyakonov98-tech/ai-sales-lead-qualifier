import tempfile
import unittest
from pathlib import Path

from sen_m001.database import Database
from sen_m001.service import LeadQualifierService
from tests.test_domain import FIXED_FORM


class PreApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "factory.db"
        self.database = Database(self.database_path)
        self.database.initialize()
        self.service = LeadQualifierService(self.database)

    def tearDown(self):
        self.database.close()
        self.temporary_directory.cleanup()

    def test_fixed_lead_stops_before_any_side_effect(self):
        result = self.service.submit_form(FIXED_FORM)

        self.assertEqual("AWAITING_HUMAN_APPROVAL", result["state"])
        self.assertEqual(100, result["score"])
        self.assertEqual("QUALIFIED", result["decision"])
        self.assertEqual("SCHEDULE_DISCOVERY_CALL", result["next_action"])
        self.assertEqual(64, len(result["candidate_sha256"]))
        self.assertEqual(0, self.database.count_crm_rows(result["run_id"]))
        self.assertEqual(0, self.database.count_artifacts(result["run_id"]))
        self.assertEqual(
            [
                "LEAD_RECEIVED",
                "LEAD_NORMALIZED",
                "LEAD_EXTRACTED",
                "LEAD_QUALIFIED",
                "APPROVAL_REQUESTED",
            ],
            self.database.evidence_types(result["run_id"]),
        )

    def test_pending_candidate_survives_database_restart_without_regeneration(self):
        pending = self.service.submit_form(FIXED_FORM)
        self.database.close()

        reopened = Database(self.database_path)
        reopened.initialize()
        recovered = LeadQualifierService(reopened).get_run(pending["run_id"])

        self.assertEqual("AWAITING_HUMAN_APPROVAL", recovered["state"])
        self.assertEqual(pending["candidate_sha256"], recovered["candidate_sha256"])
        self.assertEqual(pending["response_draft"], recovered["response_draft"])
        reopened.close()


if __name__ == "__main__":
    unittest.main()
