from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from security_lab.application import application, evaluate_case


class SecurityLabTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.previous_database = os.environ.get("SECURITY_LAB_DATABASE")
        os.environ["SECURITY_LAB_DATABASE"] = str(Path(self.tempdir.name) / "receipts.sqlite3")

    def tearDown(self):
        if self.previous_database is None:
            os.environ.pop("SECURITY_LAB_DATABASE", None)
        else:
            os.environ["SECURITY_LAB_DATABASE"] = self.previous_database
        self.tempdir.cleanup()

    def request(self, path="/", method="GET", payload=None, host="127.0.0.1", origin=""):
        body = json.dumps(payload).encode() if payload is not None else b""
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "HTTP_HOST": host,
            "HTTP_ORIGIN": origin,
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/json",
            "wsgi.input": io.BytesIO(body),
        }
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        result = b"".join(application(environ, start_response))
        return captured["status"], captured["headers"], result

    def test_minimum_request_releases_only_three_fields(self):
        receipt = evaluate_case("minimum")
        self.assertEqual(receipt["decision"], "approved")
        self.assertEqual(receipt["released_fields"], ["invoice_date", "due_date", "payment_status"])
        self.assertIn("bank_details", receipt["withheld_fields"])
        self.assertEqual(receipt["actual_reads"], 1)
        self.assertTrue(receipt["temporary_context_deleted"])

    def test_overbroad_prompt_injection_is_denied_without_release(self):
        receipt = evaluate_case("overbroad")
        self.assertEqual(receipt["decision"], "denied")
        self.assertEqual(receipt["released_fields"], [])
        self.assertEqual(receipt["actual_reads"], 0)
        self.assertEqual(receipt["result_state"], "blocked")

    def test_owner_approval_is_explicit_and_produces_a_distinct_receipt(self):
        waiting = evaluate_case("approval")
        approved = evaluate_case("approval", owner_approved=True)
        self.assertEqual(waiting["decision"], "owner_approval_required")
        self.assertEqual(waiting["released_fields"], [])
        self.assertEqual(approved["decision"], "approved_with_owner_approval")
        self.assertIn("correspondence", approved["released_fields"])
        self.assertNotEqual(waiting["receipt_id"], approved["receipt_id"])

    def test_expiry_read_limit_and_incomplete_states_are_honest(self):
        self.assertEqual(evaluate_case("expired")["decision"], "denied")
        self.assertEqual(evaluate_case("read-limit")["decision"], "denied")
        incomplete = evaluate_case("incomplete")
        self.assertEqual(incomplete["decision"], "approved")
        self.assertEqual(incomplete["result_state"], "incomplete")

    def test_receipt_is_idempotent_and_persists(self):
        first = evaluate_case("minimum")
        second = evaluate_case("minimum")
        self.assertEqual(first["receipt_id"], second["receipt_id"])
        self.assertEqual(first["created_at"], second["created_at"])
        status, headers, body = self.request(first["share_url"])
        self.assertTrue(status.startswith("200"))
        self.assertIn(b"Synthetic privacy receipt", body)
        self.assertEqual(headers["X-Robots-Tag"], "noindex, nofollow")

    def test_home_is_indexable_without_cookie_or_upload(self):
        status, headers, body = self.request("/")
        self.assertTrue(status.startswith("200"))
        self.assertIn(b"Give the agent the task", body)
        self.assertNotIn(b'type="file"', body)
        self.assertNotIn("Set-Cookie", headers)
        self.assertEqual(headers["X-Robots-Tag"], "index, follow")

    def test_api_rejects_unknown_scenario_and_cross_origin(self):
        status, _, _ = self.request("/api/evaluate/", "POST", {"scenario": "unknown"})
        self.assertTrue(status.startswith("400"))
        status, _, _ = self.request(
            "/api/evaluate/",
            "POST",
            {"scenario": "minimum"},
            origin="https://attacker.example",
        )
        self.assertTrue(status.startswith("403"))

    def test_host_allowlist_and_static_allowlist(self):
        status, _, _ = self.request("/", host="attacker.example")
        self.assertTrue(status.startswith("400"))
        status, _, _ = self.request("/static/../../policy.yaml")
        self.assertTrue(status.startswith("404"))

    def test_sitemap_contains_public_pages_but_not_receipts(self):
        status, _, body = self.request("/sitemap.xml")
        self.assertTrue(status.startswith("200"))
        self.assertIn(b"/least-privilege/", body)
        self.assertNotIn(b"/receipt/", body)


if __name__ == "__main__":
    unittest.main()
