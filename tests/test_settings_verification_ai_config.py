from __future__ import annotations

import unittest

from tests._import_app import clear_login_attempts, import_web_app_module


class SettingsVerificationAiConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("verification_ai_enabled", "false")
            settings_repo.set_setting("verification_ai_base_url", "")
            settings_repo.set_setting("verification_ai_api_key", "")
            settings_repo.set_setting("verification_ai_model", "")

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def test_get_settings_exposes_verification_ai_fields(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        settings = resp.get_json().get("settings", {})

        self.assertIn("verification_ai_enabled", settings)
        self.assertIn("verification_ai_base_url", settings)
        self.assertIn("verification_ai_model", settings)
        self.assertIn("verification_ai_api_key_set", settings)
        self.assertIn("verification_ai_api_key_masked", settings)

    def test_put_settings_can_save_verification_ai_config(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={
                "verification_ai_enabled": True,
                "verification_ai_base_url": "https://api.example.com/v1/chat/completions",
                "verification_ai_api_key": "sk-test-123456",
                "verification_ai_model": "gpt-4.1-mini",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        resp2 = client.get("/api/settings")
        settings = resp2.get_json().get("settings", {})
        self.assertTrue(settings.get("verification_ai_enabled"))
        self.assertEqual(
            settings.get("verification_ai_base_url"),
            "https://api.example.com/v1/chat/completions",
        )
        self.assertEqual(settings.get("verification_ai_model"), "gpt-4.1-mini")
        self.assertTrue(settings.get("verification_ai_api_key_set"))
        self.assertNotEqual(settings.get("verification_ai_api_key_masked"), "sk-test-123456")

    def test_put_settings_requires_complete_ai_config_when_enabled(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={
                "verification_ai_enabled": True,
                "verification_ai_base_url": "",
                "verification_ai_api_key": "",
                "verification_ai_model": "",
            },
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertFalse(body.get("success"))
        self.assertEqual(
            (body.get("error") or {}).get("code"),
            "VERIFICATION_AI_CONFIG_INCOMPLETE",
        )


if __name__ == "__main__":
    unittest.main()
