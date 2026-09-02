import re
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from sen_m001.cas import ContentAddressedStore
from sen_m001.__main__ import build_service
from sen_m001.database import Database
from sen_m001.service import LeadQualifierService
from sen_m001.web import create_server
from tests.test_domain import FIXED_FORM


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.database = Database(root / "factory.db")
        self.database.initialize()
        self.service = LeadQualifierService(
            self.database, ContentAddressedStore(root / "cas")
        )
        self.server = create_server(self.service, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.database.close()
        self.temporary_directory.cleanup()

    def _post(self, path, values):
        request = urllib.request.Request(
            self.base_url + path,
            data=urllib.parse.urlencode(values).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return urllib.request.urlopen(request, timeout=2)

    def test_local_form_reaches_approval_then_completed_verified_result(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=2) as response:
            home = response.read().decode("utf-8")
        for field in FIXED_FORM:
            self.assertIn(f'name="{field}"', home)

        with self._post("/runs", FIXED_FORM) as response:
            pending_page = response.read().decode("utf-8")
            pending_url = response.geturl()
        self.assertIn("AWAITING_HUMAN_APPROVAL", pending_page)
        run_id = re.search(r"/runs/(run-[0-9a-f-]+)$", pending_url).group(1)
        candidate_sha256 = self.service.get_run(run_id)["candidate_sha256"]

        with self._post(
            f"/runs/{run_id}/approve",
            {"candidate_sha256": candidate_sha256},
        ) as response:
            completed_page = response.read().decode("utf-8")

        self.assertIn("COMPLETED", completed_page)
        self.assertIn("VERIFIED", completed_page)
        self.assertEqual(1, self.database.count_crm_rows(run_id))

    def test_result_page_escapes_lead_content(self):
        dangerous = {**FIXED_FORM, "name": "<script>alert(1)</script>"}

        with self._post("/runs", dangerous) as response:
            page = response.read().decode("utf-8")

        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_launcher_builds_durable_service_inside_selected_data_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            service = build_service(Path(temporary_directory))
            pending = service.submit_form(FIXED_FORM)

            self.assertEqual("AWAITING_HUMAN_APPROVAL", pending["state"])
            self.assertTrue((Path(temporary_directory) / "factory.db").exists())
            service.database.close()


if __name__ == "__main__":
    unittest.main()
