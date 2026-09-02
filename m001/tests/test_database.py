import tempfile
import unittest
from pathlib import Path

from sen_m001.database import Database


RUN = {
    "run_id": "run-test-001",
    "state": "AWAITING_HUMAN_APPROVAL",
    "candidate_sha256": "a" * 64,
    "created_at": "2026-09-02T12:00:00+00:00",
    "updated_at": "2026-09-02T12:00:01+00:00",
}
DOCUMENT = {
    "document_id": "doc-test-001",
    "run_id": RUN["run_id"],
    "document_type": "lead_decision_candidate_v1",
    "revision": 1,
    "content": {"candidate_sha256": "a" * 64, "score": 100},
    "content_sha256": "b" * 64,
    "created_at": "2026-09-02T12:00:01+00:00",
}
EVIDENCE = {
    "evidence_id": "evidence-test-001",
    "run_id": RUN["run_id"],
    "evidence_type": "APPROVAL_REQUESTED",
    "subject_id": DOCUMENT["document_id"],
    "input_hashes": ["a" * 64],
    "output_hashes": ["b" * 64],
    "metadata": {"state": "AWAITING_HUMAN_APPROVAL"},
    "created_at": "2026-09-02T12:00:01+00:00",
}
EVENT = {
    "event_id": "event-test-001",
    "run_id": RUN["run_id"],
    "event_type": "RUN_STATE_CHANGED",
    "actor_type": "KERNEL",
    "actor_id": None,
    "subject_id": RUN["run_id"],
    "payload": {"to": "AWAITING_HUMAN_APPROVAL"},
    "created_at": "2026-09-02T12:00:01+00:00",
}


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "factory.db"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_wal_database_reopens_exact_current_state(self):
        database = Database(self.path)
        database.initialize()
        with database.transaction() as connection:
            database.insert_run(connection, RUN)
            database.insert_document(connection, DOCUMENT)
            database.append_evidence(connection, EVIDENCE)
            database.append_event(connection, EVENT)
        self.assertEqual("wal", database.journal_mode())
        database.close()

        reopened = Database(self.path)
        reopened.initialize()

        self.assertEqual(RUN, reopened.get_run(RUN["run_id"]))
        self.assertEqual(
            DOCUMENT,
            reopened.get_document(RUN["run_id"], "lead_decision_candidate_v1"),
        )
        self.assertEqual(["APPROVAL_REQUESTED"], reopened.evidence_types(RUN["run_id"]))
        self.assertEqual(["RUN_STATE_CHANGED"], reopened.event_types(RUN["run_id"]))
        self.assertEqual(0, reopened.count_crm_rows(RUN["run_id"]))
        self.assertEqual(0, reopened.count_artifacts(RUN["run_id"]))
        reopened.close()

    def test_transaction_rolls_back_all_writes_on_error(self):
        database = Database(self.path)
        database.initialize()

        with self.assertRaisesRegex(RuntimeError, "abort"):
            with database.transaction() as connection:
                database.insert_run(connection, RUN)
                raise RuntimeError("abort")

        self.assertIsNone(database.get_run(RUN["run_id"]))
        database.close()


if __name__ == "__main__":
    unittest.main()
