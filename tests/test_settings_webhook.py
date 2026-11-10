from __future__ import annotations

import unittest
from unittest.mock import patch

from outlook_web.security.crypto import decrypt_data, encrypt_data
from tests._import_app import clear_login_attempts, import_web_app_module


class SettingsWebhookApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("webhook_notification_enabled", "false")
            settings_repo.set_setting("webhook_notification_url", "")
            settings_repo.set_setting("webhook_notification_token", "")

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def test_get_settings_contains_webhook_fields(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        settings = resp.get_json().get("settings", {})
        self.assertIn("webhook_notification_enabled", settings)
        self.assertIn("webhook_notification_url", settings)
        self.assertIn("webhook_notification_token", settings)

    def test_update_settings_webhook_enabled_requires_url(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={"webhook_notification_enabled": True, "webhook_notification_url": ""},
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json() or {}
        self.assertFalse(body.get("success"))
        self.assertEqual((body.get("error") or {}).get("code"), "WEBHOOK_URL_REQUIRED")

    def test_update_settings_webhook_rejects_invalid_scheme(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={
                "webhook_notification_enabled": True,
                "webhook_notification_url": "ftp://example.com/hook",
            },
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json() or {}
        self.assertFalse(body.get("success"))
        self.assertEqual((body.get("error") or {}).get("code"), "WEBHOOK_URL_INVALID")

    def test_update_settings_webhook_accepts_http_and_https(self):
        client = self.app.test_client()
        self._login(client)

        for url in ("http://example.com/hook", "https://example.com/hook"):
            resp = client.put(
                "/api/settings",
                json={
                    "webhook_notification_enabled": True,
                    "webhook_notification_url": url,
                },
            )
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.get_json().get("success"))

    def test_update_settings_webhook_token_encrypted_and_masked(self):
        client = self.app.test_client()
        self._login(client)

        plain = "webhook-token-123456"
        resp = client.put(
            "/api/settings",
            json={
                "webhook_notification_enabled": True,
                "webhook_notification_url": "https://example.com/hook",
                "webhook_notification_token": plain,
            },
        )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            raw = settings_repo.get_setting("webhook_notification_token", "")
            self.assertTrue(raw.startswith("enc:"))
            self.assertEqual(decrypt_data(raw), plain)

        resp2 = client.get("/api/settings")
        settings = resp2.get_json().get("settings", {})
        masked = settings.get("webhook_notification_token")
        self.assertTrue(masked)
        self.assertNotEqual(masked, plain)

    def test_update_settings_webhook_token_placeholder_keeps_existing(self):
        existing = "old-webhook-token"
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("webhook_notification_token", encrypt_data(existing))

        client = self.app.test_client()
        self._login(client)
        masked = client.get("/api/settings").get_json().get("settings", {}).get("webhook_notification_token")
        self.assertTrue(masked)

        resp = client.put(
            "/api/settings",
            json={
                "webhook_notification_enabled": True,
                "webhook_notification_url": "https://example.com/hook",
                "webhook_notification_token": masked,
            },
        )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            raw = settings_repo.get_setting("webhook_notification_token", "")
            self.assertEqual(decrypt_data(raw), existing)

    def test_update_settings_webhook_token_empty_clears_value(self):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("webhook_notification_token", encrypt_data("to-be-cleared"))

        client = self.app.test_client()
        self._login(client)
        resp = client.put(
            "/api/settings",
            json={
                "webhook_notification_enabled": True,
                "webhook_notification_url": "https://example.com/hook",
                "webhook_notification_token": "",
            },
        )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            self.assertEqual(settings_repo.get_setting("webhook_notification_token", ""), "")

    def test_webhook_test_uses_saved_settings_only(self):
        client = self.app.test_client()
        self._login(client)

        client.put(
            "/api/settings",
            json={
                "webhook_notification_enabled": True,
                "webhook_notification_url": "https://saved.example.com/hook",
                "webhook_notification_token": "saved-token",
            },
        )

        captured = {}

        def _fake_send(*, url, token, text_body, timeout_sec=10, retry=1):
            captured["url"] = url
            captured["token"] = token
            captured["text_body"] = text_body
            captured["timeout_sec"] = timeout_sec
            captured["retry"] = retry

        with patch(
            "outlook_web.services.webhook_push.send_webhook_message",
            side_effect=_fake_send,
        ):
            resp = client.post(
                "/api/settings/webhook-test",
                json={
                    "webhook_notification_url": "https://unsaved.example.com/hook",
                    "webhook_notification_token": "unsaved-token",
                },
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(captured.get("url"), "https://saved.example.com/hook")
        self.assertEqual(captured.get("token"), "saved-token")
        self.assertEqual(captured.get("timeout_sec"), 10)
        self.assertEqual(captured.get("retry"), 1)

    def test_webhook_test_returns_not_configured_when_missing(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.post("/api/settings/webhook-test", json={})
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json() or {}
        self.assertFalse(body.get("success"))
        self.assertEqual((body.get("error") or {}).get("code"), "WEBHOOK_NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
