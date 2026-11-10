import json
import unittest
import uuid

from tests._import_app import clear_login_attempts, import_web_app_module


class ExternalPoolE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db
            from outlook_web.repositories import settings as settings_repo

            db = get_db()
            db.execute("DELETE FROM audit_logs WHERE resource_type = 'external_api'")
            db.execute("DELETE FROM external_api_keys")
            db.execute("DELETE FROM external_api_consumer_usage_daily")
            db.execute(
                "DELETE FROM account_claim_logs WHERE account_id IN (SELECT id FROM accounts WHERE email LIKE '%@extpoole2e.test')"
            )
            db.execute("DELETE FROM accounts WHERE email LIKE '%@extpoole2e.test'")
            db.commit()

            settings_repo.set_setting("external_api_key", "")
            settings_repo.set_setting("external_api_public_mode", "false")
            settings_repo.set_setting("external_api_ip_whitelist", "[]")
            settings_repo.set_setting("pool_external_enabled", "true")
            settings_repo.set_setting("external_api_disable_pool_claim_random", "false")
            settings_repo.set_setting("external_api_disable_pool_claim_release", "false")
            settings_repo.set_setting("external_api_disable_pool_claim_complete", "false")
            settings_repo.set_setting("external_api_disable_pool_stats", "false")

    @staticmethod
    def _auth_headers(value: str):
        return {"X-API-Key": value}

    def _create_external_api_key(self, name: str, api_key: str, *, pool_access: bool):
        with self.app.app_context():
            from outlook_web.repositories import external_api_keys as external_api_keys_repo

            return external_api_keys_repo.create_external_api_key(
                name=name,
                api_key=api_key,
                allowed_emails=[],
                pool_access=pool_access,
                enabled=True,
            )

    def _insert_pool_account(self, *, provider: str = "outlook") -> int:
        email_addr = f"{uuid.uuid4().hex}@extpoole2e.test"
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (
                    email, password, client_id, refresh_token,
                    group_id, status, account_type, provider, pool_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_addr,
                    "pw",
                    "cid-test",
                    "rt-test",
                    1,
                    "active",
                    "outlook",
                    provider,
                    "available",
                ),
            )
            db.commit()
            row = db.execute("SELECT id FROM accounts WHERE email = ?", (email_addr,)).fetchone()
            return int(row["id"])

    def _external_audit_logs(self):
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            rows = db.execute("""
                SELECT action, resource_id, details
                FROM audit_logs
                WHERE resource_type = 'external_api'
                ORDER BY id ASC
                """).fetchall()
        return [dict(row) for row in rows]

    def _external_consumer_usage_rows(self):
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            rows = db.execute("""
                SELECT consumer_key, consumer_name, endpoint, total_count, success_count, error_count
                FROM external_api_consumer_usage_daily
                ORDER BY id ASC
                """).fetchall()
        return [dict(row) for row in rows]

    def test_external_pool_e2e_claim_complete_records_audit_and_usage(self):
        client = self.app.test_client()
        self._create_external_api_key("partner-e2e", "pool-e2e-123", pool_access=True)
        self._insert_pool_account(provider="outlook")

        claim_resp = client.post(
            "/api/external/pool/claim-random",
            headers=self._auth_headers("pool-e2e-123"),
            json={
                "caller_id": "e2e-worker-01",
                "task_id": "e2e-task-001",
                "provider": "outlook",
            },
        )
        self.assertEqual(claim_resp.status_code, 200)
        claim_data = claim_resp.get_json()["data"]

        complete_resp = client.post(
            "/api/external/pool/claim-complete",
            headers=self._auth_headers("pool-e2e-123"),
            json={
                "account_id": claim_data["account_id"],
                "claim_token": claim_data["claim_token"],
                "caller_id": "e2e-worker-01",
                "task_id": "e2e-task-001",
                "result": "success",
                "detail": "e2e-complete",
            },
        )
        self.assertEqual(complete_resp.status_code, 200)
        self.assertEqual(complete_resp.get_json()["data"]["pool_status"], "used")

        stats_resp = client.get(
            "/api/external/pool/stats",
            headers=self._auth_headers("pool-e2e-123"),
        )
        self.assertEqual(stats_resp.status_code, 200)
        stats_data = stats_resp.get_json()
        self.assertTrue(stats_data.get("success"))

        logs = self._external_audit_logs()
        self.assertGreaterEqual(len(logs), 3)
        parsed_details = [json.loads(item["details"]) for item in logs]
        endpoints = [item.get("endpoint") for item in parsed_details]
        self.assertIn("/api/external/pool/claim-random", endpoints)
        self.assertIn("/api/external/pool/claim-complete", endpoints)
        self.assertIn("/api/external/pool/stats", endpoints)
        self.assertTrue(all(item.get("consumer_name") == "partner-e2e" for item in parsed_details))

        usage_rows = self._external_consumer_usage_rows()
        self.assertEqual(len(usage_rows), 3)
        by_endpoint = {row["endpoint"]: row for row in usage_rows}
        self.assertEqual(by_endpoint["/api/external/pool/claim-random"]["success_count"], 1)
        self.assertEqual(by_endpoint["/api/external/pool/claim-complete"]["success_count"], 1)
        self.assertEqual(by_endpoint["/api/external/pool/stats"]["success_count"], 1)

    def test_external_pool_e2e_public_mode_disable_and_pool_access_chain(self):
        client = self.app.test_client()
        self._create_external_api_key("partner-deny", "pool-e2e-deny", pool_access=False)
        self._insert_pool_account(provider="outlook")

        deny_resp = client.post(
            "/api/external/pool/claim-random",
            headers=self._auth_headers("pool-e2e-deny"),
            json={
                "caller_id": "e2e-worker-02",
                "task_id": "e2e-task-002",
                "provider": "outlook",
            },
        )
        self.assertEqual(deny_resp.status_code, 403)
        self.assertEqual(deny_resp.get_json().get("code"), "FORBIDDEN")

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_public_mode", "true")
            settings_repo.set_setting("external_api_ip_whitelist", json.dumps(["127.0.0.1"]))
            settings_repo.set_setting("external_api_disable_pool_claim_random", "true")

        allow_key = self._create_external_api_key("partner-allow", "pool-e2e-allow", pool_access=True)
        self.assertIsNotNone(allow_key)

        feature_disabled_resp = client.post(
            "/api/external/pool/claim-random",
            headers=self._auth_headers("pool-e2e-allow"),
            json={
                "caller_id": "e2e-worker-03",
                "task_id": "e2e-task-003",
                "provider": "outlook",
            },
        )
        self.assertEqual(feature_disabled_resp.status_code, 403)
        data = feature_disabled_resp.get_json()
        self.assertEqual(data.get("code"), "FEATURE_DISABLED")
        self.assertEqual(data.get("data", {}).get("feature"), "pool_claim_random")

        logs = self._external_audit_logs()
        parsed_details = [json.loads(item["details"]) for item in logs]
        codes = [item.get("code") for item in parsed_details]
        self.assertIn("FORBIDDEN", codes)
