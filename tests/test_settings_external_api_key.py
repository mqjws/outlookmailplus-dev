import unittest

from tests._import_app import clear_login_attempts, import_web_app_module


class ExternalApiKeySettingsTests(unittest.TestCase):
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
            db.execute("DELETE FROM external_api_keys")
            db.execute("DELETE FROM external_api_consumer_usage_daily")
            db.commit()
            settings_repo.set_setting("external_api_key", "")
            settings_repo.set_setting("pool_external_enabled", "false")
            settings_repo.set_setting("external_api_disable_pool_claim_random", "false")
            settings_repo.set_setting("external_api_disable_pool_claim_release", "false")
            settings_repo.set_setting("external_api_disable_pool_claim_complete", "false")
            settings_repo.set_setting("external_api_disable_pool_stats", "false")

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def test_get_settings_exposes_external_api_key_status_and_masked_value(self):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_key", "abcdef1234567890")

        client = self.app.test_client()
        self._login(client)
        resp = client.get("/api/settings")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        settings = data.get("settings", {})
        self.assertIn("external_api_key_set", settings)
        self.assertIn("external_api_key_masked", settings)
        self.assertTrue(settings.get("external_api_key_set"))
        self.assertNotEqual(settings.get("external_api_key_masked"), "abcdef1234567890")

    def test_put_settings_can_update_external_api_key(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put("/api/settings", json={"external_api_key": "new-key-123"})

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))

        resp2 = client.get("/api/settings")
        self.assertEqual(resp2.status_code, 200)
        settings = resp2.get_json().get("settings", {})
        self.assertTrue(settings.get("external_api_key_set"))

    def test_clearing_external_api_key_marks_open_api_as_not_configured(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put("/api/settings", json={"external_api_key": ""})

        self.assertEqual(resp.status_code, 200)
        resp2 = client.get("/api/settings")
        settings = resp2.get_json().get("settings", {})
        self.assertFalse(settings.get("external_api_key_set"))

    def test_put_settings_does_not_overwrite_when_sending_masked_placeholder(self):
        original = "abcdef1234567890"
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_key", original)

        client = self.app.test_client()
        self._login(client)

        resp1 = client.get("/api/settings")
        self.assertEqual(resp1.status_code, 200)
        masked = resp1.get_json().get("settings", {}).get("external_api_key_masked")
        self.assertTrue(masked)
        self.assertNotEqual(masked, original)

        resp2 = client.put("/api/settings", json={"external_api_key": masked})
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.get_json().get("success"))

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            self.assertEqual(settings_repo.get_external_api_key(), original)

    def test_get_settings_exposes_external_api_keys_list(self):
        with self.app.app_context():
            from outlook_web.repositories import external_api_keys as external_api_keys_repo

            external_api_keys_repo.create_external_api_key(
                name="partner-a",
                api_key="multi-key-123",
                allowed_emails=["user1@example.com"],
                pool_access=True,
                enabled=True,
            )

        client = self.app.test_client()
        self._login(client)
        resp = client.get("/api/settings")

        self.assertEqual(resp.status_code, 200)
        settings = resp.get_json().get("settings", {})
        self.assertTrue(settings.get("external_api_multi_key_set"))
        self.assertEqual(settings.get("external_api_keys_count"), 1)
        self.assertEqual(settings.get("external_api_keys", [])[0]["name"], "partner-a")
        self.assertEqual(
            settings.get("external_api_keys", [])[0]["allowed_emails"],
            ["user1@example.com"],
        )
        self.assertTrue(settings.get("external_api_keys", [])[0]["pool_access"])

    def test_put_settings_can_replace_external_api_keys(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={
                "external_api_keys": [
                    {
                        "name": "partner-a",
                        "api_key": "multi-key-123",
                        "allowed_emails": ["user1@example.com"],
                        "pool_access": True,
                        "enabled": True,
                    },
                    {
                        "name": "partner-b",
                        "api_key": "multi-key-456",
                        "allowed_emails": [],
                        "pool_access": False,
                        "enabled": False,
                    },
                ]
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        resp2 = client.get("/api/settings")
        settings = resp2.get_json().get("settings", {})
        self.assertEqual(settings.get("external_api_keys_count"), 2)
        keys = settings.get("external_api_keys", [])
        self.assertEqual(keys[0]["name"], "partner-a")
        self.assertTrue(keys[0]["enabled"])
        self.assertTrue(keys[0]["pool_access"])
        self.assertEqual(keys[1]["name"], "partner-b")
        self.assertFalse(keys[1]["enabled"])
        self.assertFalse(keys[1]["pool_access"])

    def test_put_settings_rolls_back_external_api_keys_when_other_field_invalid(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={
                "external_api_keys": [
                    {
                        "name": "partner-a",
                        "api_key": "multi-key-123",
                        "allowed_emails": ["user1@example.com"],
                        "enabled": True,
                    }
                ],
                "refresh_interval_days": 0,
            },
        )

        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.get_json().get("success"))

        resp2 = client.get("/api/settings")
        settings = resp2.get_json().get("settings", {})
        self.assertEqual(settings.get("external_api_keys_count"), 0)
        self.assertEqual(settings.get("external_api_keys"), [])

    def test_put_settings_parses_string_false_for_external_api_keys_enabled(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={
                "external_api_keys": [
                    {
                        "name": "partner-a",
                        "api_key": "multi-key-123",
                        "allowed_emails": [],
                        "pool_access": True,
                        "enabled": "false",
                    }
                ]
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        resp2 = client.get("/api/settings")
        settings = resp2.get_json().get("settings", {})
        self.assertEqual(settings.get("external_api_keys_count"), 1)
        self.assertFalse(settings.get("external_api_keys", [])[0]["enabled"])

    def test_get_settings_exposes_pool_external_enabled(self):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")

        client = self.app.test_client()
        self._login(client)
        resp = client.get("/api/settings")

        self.assertEqual(resp.status_code, 200)
        settings = resp.get_json().get("settings", {})
        self.assertTrue(settings.get("pool_external_enabled"))

    def test_put_settings_can_update_pool_external_enabled(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put("/api/settings", json={"pool_external_enabled": True})

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        resp2 = client.get("/api/settings")
        self.assertEqual(resp2.status_code, 200)
        settings = resp2.get_json().get("settings", {})
        self.assertTrue(settings.get("pool_external_enabled"))

    def test_get_settings_exposes_pool_feature_disable_flags(self):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_disable_pool_claim_random", "true")
            settings_repo.set_setting("external_api_disable_pool_stats", "true")

        client = self.app.test_client()
        self._login(client)
        resp = client.get("/api/settings")

        self.assertEqual(resp.status_code, 200)
        settings = resp.get_json().get("settings", {})
        self.assertTrue(settings.get("external_api_disable_pool_claim_random"))
        self.assertTrue(settings.get("external_api_disable_pool_stats"))

    def test_put_settings_can_update_pool_feature_disable_flags(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={
                "external_api_disable_pool_claim_random": True,
                "external_api_disable_pool_stats": True,
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        resp2 = client.get("/api/settings")
        settings = resp2.get_json().get("settings", {})
        self.assertTrue(settings.get("external_api_disable_pool_claim_random"))
        self.assertTrue(settings.get("external_api_disable_pool_stats"))


if __name__ == "__main__":
    unittest.main()
