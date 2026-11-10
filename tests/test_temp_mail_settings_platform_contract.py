from __future__ import annotations

import unittest
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class TempMailSettingsPlatformContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("temp_mail_provider", "custom_domain_temp_mail")
            settings_repo.set_setting("temp_mail_api_base_url", "https://platform-settings.test")
            settings_repo.set_setting("temp_mail_api_key", "platform-secret")
            settings_repo.set_setting("gptmail_api_key", "legacy-secret")
            settings_repo.set_setting(
                "temp_mail_domains",
                '[{"name":"settings-platform.test","enabled":true}]',
            )
            settings_repo.set_setting("temp_mail_default_domain", "settings-platform.test")
            settings_repo.set_setting(
                "temp_mail_prefix_rules",
                '{"min_length":2,"max_length":20,"pattern":"^[a-z0-9-]+$"}',
            )

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)

    def test_get_settings_exposes_formal_temp_mail_fields_only(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/api/settings")

        self.assertEqual(resp.status_code, 200)
        settings = resp.get_json()["settings"]
        self.assertEqual(settings["temp_mail_provider"], "custom_domain_temp_mail")
        self.assertEqual(settings["temp_mail_provider_label"], "temp_mail")
        self.assertTrue(settings["temp_mail_api_key_set"])
        self.assertNotIn("gptmail_api_key_set", settings)
        self.assertEqual(settings["temp_mail_domains"][0]["name"], "settings-platform.test")

    def test_put_empty_temp_mail_api_key_does_not_clear_existing_value(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put("/api/settings", json={"temp_mail_api_key": ""})

        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            self.assertEqual(settings_repo.get_setting("temp_mail_api_key"), "platform-secret")
            self.assertEqual(settings_repo.get_setting("gptmail_api_key"), "legacy-secret")

    def test_db_settings_take_priority_over_env_fallback(self):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            with patch("outlook_web.config.get_temp_mail_api_key_default", return_value="env-secret"):
                value = settings_repo.get_temp_mail_api_key()

        self.assertEqual(value, "platform-secret")

    def test_runtime_provider_selection_matches_saved_formal_provider(self):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo
            from outlook_web.services.temp_mail_provider_factory import get_temp_mail_provider

            provider = get_temp_mail_provider()
            self.assertEqual(settings_repo.get_temp_mail_provider(), "custom_domain_temp_mail")
            self.assertEqual(provider.provider_name, "custom_domain_temp_mail")

    def test_put_rejects_invalid_temp_mail_provider_before_runtime(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put("/api/settings", json={"temp_mail_provider": "unknown-provider"})

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"]["code"], "TEMP_MAIL_PROVIDER_INVALID")

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            self.assertEqual(settings_repo.get_setting("temp_mail_provider"), "custom_domain_temp_mail")
