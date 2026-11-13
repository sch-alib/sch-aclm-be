"""Local workflow checks; always run against a temporary DB and mock CA."""

import os
import tempfile
import unittest
from unittest.mock import patch

# Must be set before importing app.config and its database engine.
_tempdir = tempfile.TemporaryDirectory(prefix="aclm-test-")
os.environ["DATABASE_PATH"] = os.path.join(_tempdir.name, "test.db")
os.environ["ARTIFACTS_DIRECTORY"] = os.path.join(_tempdir.name, "artifacts")
os.environ["DIGICERT_MODE"] = "mock"
os.environ["ISSUANCE_CHECK_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "unit-test-secret-at-least-32-bytes-long"
TEST_PASSWORD = "test-only-password-not-for-deployment"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = TEST_PASSWORD

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def make_csr(common_name="new.example.com", sans=("www.new.example.com",)):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    ).add_extension(x509.SubjectAlternativeName([x509.DNSName(san) for san in sans]), critical=False)
    return builder.sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode()


class CertificateWorkflows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()
        # Only an initial admin is bootstrapped by the application. Add other
        # roles explicitly in this temporary test database.
        from app.core.security import hash_password
        from app.database.session import SessionFactory
        from app.models.user import User
        with SessionFactory() as session:
            from datetime import datetime, timedelta, timezone
            from app.models.certificate import Certificate
            from app.models.target import Target
            session.add_all([
                User(username=name, full_name=name, role=role,
                     password_hash=hash_password(TEST_PASSWORD))
                for name, role in (("operator", "Operator"), ("viewer", "Viewer"))
            ])
            sample = Certificate(
                common_name="managed.company.com", sans="managed.company.com",
                ca_type="digicert", external_order_id="9001",
                external_certificate_id="9101", management_state="Managed",
                status="Active", csr_pem="MOCK_CSR",
                valid_to=datetime.now(timezone.utc) + timedelta(days=18),
            )
            sample.targets.append(Target(
                name="IIS-WEB-01", adapter_type="iis", host="web01.company.local",
                site_name="Default Web Site", hostname="managed.company.com", port=443,
            ))
            session.add(sample)
            session.commit()
        cls.admin = cls.login("admin")
        cls.operator = cls.login("operator")
        cls.viewer = cls.login("viewer")

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)
        from app.database.session import engine
        engine.dispose()
        _tempdir.cleanup()

    @classmethod
    def login(cls, username):
        response = cls.client.post("/api/v1/auth/login", json={
            "username": username, "password": TEST_PASSWORD,
        })
        assert response.status_code == 200, response.text
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    def test_external_details_and_onboarding_save_expiry(self):
        from datetime import date

        external_url = "/api/v1/external/digicert/9002"
        response = self.client.get(external_url, headers=self.admin)
        self.assertEqual(response.status_code, 200, response.text)
        details = response.json()["external"]
        self.assertTrue(details["certificate"]["valid_till"])
        self.assertEqual(details["certificate"]["valid_till"], details["valid_till"])

        response = self.client.post(external_url + "/onboard", headers=self.operator,
            json={"host": "web02.company.local", "hostname": "discovered.company.com",
                  "reason": "Approved onboarding"})
        self.assertEqual(response.status_code, 200, response.text)
        expiry = response.json()["valid_to"]
        self.assertEqual(date.fromisoformat(expiry[:10]).isoformat(), details["valid_till"])
        managed = self.client.get(f"/api/v1/certificates/{response.json()['id']}",
                                  headers=self.operator)
        self.assertEqual(managed.status_code, 200, managed.text)
        self.assertEqual(managed.json()["valid_to"], expiry)

    def test_offboard_and_reonboard(self):
        url = "/api/v1/certificates/1"
        self.assertEqual(self.client.post(url + "/offboard", headers=self.viewer,
                                          json={"reason": "Approved retirement"}).status_code, 403)
        result = self.client.post(url + "/offboard", headers=self.operator,
                                  json={"reason": "Approved retirement"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["management_state"], "Offboarded")
        record = self.client.get(url, headers=self.operator).json()
        self.assertFalse(record["targets"][0]["enabled"])
        self.assertEqual(record["status"], "Active")  # no CA revocation
        self.assertEqual(self.client.post(url + "/renew", headers=self.operator).status_code, 409)
        self.assertEqual(self.client.post(url + "/offboard", headers=self.operator,
                                          json={"reason": "Again"}).status_code, 409)
        result = self.client.post("/api/v1/external/digicert/9001/onboard", headers=self.operator,
                                  json={"host": "web01.company.local", "hostname": "managed.company.com",
                                        "reason": "Approved return"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["id"], 1)
        self.assertEqual(result.json()["management_state"], "Managed")
        record = self.client.get(url, headers=self.operator).json()
        self.assertTrue(record["targets"][0]["enabled"])
        self.assertEqual(record["targets"][0]["name"], "IIS-WEB-01")
        self.assertEqual(len(record["targets"]), 1)

    def test_new_order_remains_pending_until_issuance_confirmed(self):
        order = {
            "common_name": "new.example.com", "dns_names": ["www.new.example.com"],
            "csr_pem": make_csr(), "product_name_id": "ssl_multi_domain",
            "organization_id": 123, "validity_days": 90,
        }
        endpoint = "/api/v1/certificates"
        self.assertEqual(self.client.post(endpoint, headers=self.viewer, json=order).status_code, 403)
        result = self.client.post(endpoint, headers=self.admin, json=order)
        self.assertEqual(result.status_code, 201, result.text)
        certificate = result.json()
        self.assertEqual(certificate["management_state"], "Pending issuance")
        self.assertIsNone(certificate["external_certificate_id"])
        self.assertEqual(self.client.post(endpoint, headers=self.admin, json=order).status_code, 422)
        check_url = f"{endpoint}/{certificate['id']}/check-issuance"
        self.assertEqual(self.client.post(check_url, headers=self.viewer).status_code, 403)
        first = self.client.post(check_url, headers=self.admin)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["management_state"], "Pending issuance")
        onboard_url = f"/api/v1/external/digicert/{certificate['external_order_id']}/onboard"
        self.assertEqual(self.client.post(onboard_url, headers=self.admin,
            json={"host": "server.local", "hostname": "new.example.com",
                  "reason": "Not yet issued"}).status_code, 409)
        second = self.client.post(check_url, headers=self.admin)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["management_state"], "Managed")
        self.assertTrue(second.json()["valid_to"])
        self.assertTrue(second.json()["external_certificate_id"])
        self.assertEqual(self.client.post(check_url, headers=self.admin).status_code, 409)
        detail = self.client.get(f"{endpoint}/{certificate['id']}", headers=self.admin).json()
        self.assertEqual(detail["targets"], [])  # issuance did not deploy
        self.assertEqual(self.client.post(f"{endpoint}/{certificate['id']}/renew",
                                          headers=self.admin).status_code, 409)
        jobs = self.client.get("/api/v1/jobs", headers=self.admin).json()
        self.assertTrue(any(job["job_type"] == "NewOrder" and job["status"] == "Succeeded"
                            for job in jobs))
        offboard = self.client.post(f"{endpoint}/{certificate['id']}/offboard",
            headers=self.admin, json={"reason": "Remove from automation"})
        self.assertEqual(offboard.status_code, 200, offboard.text)
        reonboard = self.client.post(onboard_url, headers=self.admin,
            json={"host": "server.local", "hostname": "new.example.com",
                  "reason": "Approved new target"})
        self.assertEqual(reonboard.status_code, 200, reonboard.text)
        self.assertEqual(reonboard.json()["management_state"], "Managed")
        detail = self.client.get(f"{endpoint}/{certificate['id']}", headers=self.admin).json()
        self.assertEqual(len(detail["targets"]), 1)
        self.assertFalse(detail["renewal_available"])
        self.assertEqual(self.client.post(f"{endpoint}/{certificate['id']}/renew",
                                          headers=self.admin).status_code, 409)

    def test_new_order_payload_and_no_automatic_post_retry(self):
        import httpx
        from app.adapters.ca.digicert import DigiCertAdapter
        adapter = DigiCertAdapter()
        requests = []

        def fake_request(**kwargs):
            requests.append(kwargs)
            return httpx.Response(200, json={"id": 1001},
                request=httpx.Request("POST", "https://invalid.example"))

        with patch.object(adapter, "_is_mock_mode", return_value=False), \
             patch.object(adapter, "_request", side_effect=fake_request):
            result = adapter.order_certificate("new.example.com", ["www.new.example.com"],
                                               make_csr(), "ssl_multi_domain", 123, 90)
        self.assertEqual(result["id"], 1001)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["path"], "/order/certificate/ssl_multi_domain")
        self.assertEqual(requests[0]["json_body"]["order_validity"], {"days": 90})
        self.assertEqual(requests[0]["json_body"]["organization"], {"id": 123})
        self.assertFalse(requests[0]["json_body"]["skip_approval"])
        self.assertFalse(requests[0]["retry"])

    def _submit_order(self):
        response = self.client.post("/api/v1/certificates", headers=self.admin, json={
            "common_name": "new.example.com", "dns_names": ["www.new.example.com"],
            "csr_pem": make_csr(), "product_name_id": "ssl_multi_domain",
            "organization_id": 123, "validity_days": 90,
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_automatic_checks_wait_then_confirm_issuance_without_deployment(self):
        from datetime import datetime, timedelta
        from app.services.issuance_monitor import issuance_monitor
        certificate = self._submit_order()
        detail_url = f"/api/v1/certificates/{certificate['id']}"
        scheduled = self.client.get(detail_url, headers=self.admin).json()["issuance_check"]
        self.assertEqual(scheduled["status"], "Pending")
        self.assertIsNone(scheduled["last_error"])
        due = datetime.fromisoformat(scheduled["next_check_at"]).replace(tzinfo=None)
        self.assertGreaterEqual(issuance_monitor.run_due_checks(now=due), 1)
        self.assertEqual(issuance_monitor.run_due_checks(now=due), 0)
        pending = self.client.get(detail_url, headers=self.admin).json()
        self.assertEqual(pending["management_state"], "Pending issuance")
        self.assertEqual(pending["issuance_check"]["status"], "Pending")
        self.assertEqual(pending["issuance_check"]["consecutive_failures"], 0)
        self.assertTrue(pending["issuance_check"]["last_checked_at"].endswith("+00:00"))
        issuance_monitor.run_due_checks(now=due + timedelta(minutes=2))
        issued = self.client.get(detail_url, headers=self.admin).json()
        self.assertEqual(issued["management_state"], "Managed")
        self.assertEqual(issued["issuance_check"]["status"], "Issued")
        self.assertIsNone(issued["issuance_check"]["next_check_at"])
        self.assertEqual(issued["targets"], [])
        self.assertFalse(issued["renewal_available"])
        jobs = self.client.get("/api/v1/jobs", headers=self.admin).json()
        self.assertTrue(any(job["certificate_id"] == certificate["id"] and
                            job["status"] == "Succeeded" for job in jobs))

    def test_rejected_order_is_terminal_not_retried(self):
        from datetime import datetime, timedelta
        from app.adapters.registry import adapter_registry
        from app.services.issuance_monitor import issuance_monitor
        certificate = self._submit_order()
        detail_url = f"/api/v1/certificates/{certificate['id']}"
        due = datetime.fromisoformat(self.client.get(detail_url, headers=self.admin)
            .json()["issuance_check"]["next_check_at"]).replace(tzinfo=None)
        adapter = adapter_registry.get_ca_adapter("digicert")
        with patch.object(adapter, "get_order_details", return_value={"status": "rejected"}):
            issuance_monitor.run_due_checks(now=due)
        detail = self.client.get(detail_url, headers=self.admin).json()
        self.assertEqual(detail["management_state"], "Order failed")
        self.assertEqual(detail["issuance_check"]["status"], "Failed")
        self.assertIsNone(detail["issuance_check"]["next_check_at"])
        self.assertNotEqual(detail["status"], "Active")
        self.assertEqual(self.client.post(detail_url + "/check-issuance",
            headers=self.admin).status_code, 409)
        issuance_monitor.run_due_checks(now=due + timedelta(days=1))
        self.assertEqual(self.client.get(detail_url, headers=self.admin).json()
                         ["issuance_check"]["status"], "Failed")

    def test_retries_backoff_error_redaction_and_manual_recovery(self):
        from datetime import datetime, timedelta
        from app.adapters.registry import adapter_registry
        from app.core.config import settings
        from app.core.exceptions import DigiCertApiError
        from app.services.issuance_monitor import issuance_monitor
        certificate = self._submit_order()
        detail_url = f"/api/v1/certificates/{certificate['id']}"
        due = datetime.fromisoformat(self.client.get(detail_url, headers=self.admin)
                                     .json()["issuance_check"]["next_check_at"]).replace(tzinfo=None)
        adapter = adapter_registry.get_ca_adapter("digicert")
        with patch.object(settings, "issuance_check_max_failures", 3), \
             patch.object(settings, "issuance_check_interval_seconds", 2), \
             patch.object(settings, "issuance_check_max_backoff_seconds", 4), \
             patch.object(adapter, "get_order_details", side_effect=DigiCertApiError(
                 "DigiCert API returned 503: private-key=DO_NOT_LEAK")):
            for attempt, timestamp in enumerate((due, due + timedelta(seconds=2),
                                                  due + timedelta(seconds=6)), 1):
                issuance_monitor.run_due_checks(now=timestamp)
                check = self.client.get(detail_url, headers=self.admin).json()["issuance_check"]
                self.assertEqual(check["consecutive_failures"], attempt)
                self.assertEqual(check["status"], "Needs attention" if attempt == 3 else "Retrying")
                self.assertIn("503", check["last_error"])
                self.assertNotIn("DO_NOT_LEAK", check["last_error"])
                if attempt < 3:
                    next_due = datetime.fromisoformat(check["next_check_at"]).replace(tzinfo=None)
                    self.assertEqual(next_due, timestamp + timedelta(seconds=2 if attempt == 1 else 4))
            issuance_monitor.run_due_checks(now=due + timedelta(days=1))
            self.assertEqual(self.client.get(detail_url, headers=self.admin).json()
                             ["issuance_check"]["status"], "Needs attention")
        failed_jobs = self.client.get("/api/v1/jobs", headers=self.admin).json()
        self.assertTrue(any(job["certificate_id"] == certificate["id"] and
                            job["status"] == "Failed" and "503" in job["message"]
                            for job in failed_jobs))
        # The check failed, not the DigiCert order: manual retry can recover it.
        response = self.client.post(detail_url + "/check-issuance", headers=self.admin)
        self.assertEqual(response.status_code, 200, response.text)
        check = self.client.get(detail_url, headers=self.admin).json()["issuance_check"]
        self.assertEqual(check["status"], "Pending")
        self.assertEqual(check["consecutive_failures"], 0)
        self.assertIsNone(check["last_error"])
        jobs = self.client.get("/api/v1/jobs", headers=self.admin).json()
        self.assertTrue(any(job["certificate_id"] == certificate["id"] and
                            job["status"] == "Pending" for job in jobs))

    def test_background_thread_confirms_mock_issuance(self):
        import time
        from app.core.config import settings
        from app.services.issuance_monitor import issuance_monitor
        with patch.object(settings, "issuance_check_enabled", True), \
             patch.object(settings, "issuance_check_interval_seconds", 1), \
             patch.object(settings, "issuance_check_tick_seconds", 1):
            certificate = self._submit_order()
            detail_url = f"/api/v1/certificates/{certificate['id']}"
            issuance_monitor.start()
            try:
                deadline = time.monotonic() + 7
                while time.monotonic() < deadline:
                    if self.client.get(detail_url, headers=self.admin).json()["management_state"] == "Managed":
                        break
                    time.sleep(0.25)
                detail = self.client.get(detail_url, headers=self.admin).json()
                self.assertEqual(detail["management_state"], "Managed")
                self.assertEqual(detail["issuance_check"]["status"], "Issued")
                self.assertEqual(detail["targets"], [])
            finally:
                issuance_monitor.stop()

    def test_lease_prevents_duplicate_checks_and_backfills_old_pending(self):
        from datetime import timedelta
        from app.database.session import SessionFactory
        from app.models.issuance_check import IssuanceCheck
        from app.services.issuance_monitor import issuance_monitor, utcnow
        certificate = self._submit_order()
        with SessionFactory() as session:
            session.delete(session.get(IssuanceCheck, certificate["id"]))
            session.commit()
            issuance_monitor.schedule_existing(session)
            check = session.get(IssuanceCheck, certificate["id"])
            self.assertIsNotNone(check)
            check.lease_token = "other-worker"
            check.lease_until = utcnow() + timedelta(minutes=5)
            session.commit()
        response = self.client.post(
            f"/api/v1/certificates/{certificate['id']}/check-issuance", headers=self.admin)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(issuance_monitor.run_due_checks(now=utcnow()), 0)

    def test_rejects_mismatched_or_invalid_csr_without_order(self):
        body = {
            "common_name": "wrong.example.com", "dns_names": ["www.new.example.com"],
            "csr_pem": make_csr(), "product_name_id": "ssl_plus",
            "organization_id": 123, "validity_days": 90,
        }
        result = self.client.post("/api/v1/certificates", headers=self.admin, json=body)
        self.assertEqual(result.status_code, 422, result.text)
        body["common_name"] = "new.example.com"
        body["dns_names"] = ["different.example.com"]
        self.assertEqual(self.client.post("/api/v1/certificates", headers=self.admin,
                                          json=body).status_code, 422)
        body["dns_names"] = ["www.new.example.com"]
        body["product_name_id"] = "../reissue"
        self.assertEqual(self.client.post("/api/v1/certificates", headers=self.admin,
                                          json=body).status_code, 422)


if __name__ == "__main__":
    unittest.main()
