import unittest
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class SettingsPasswordChangeGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo
            from outlook_web.security.crypto import hash_password

            settings_repo.set_setting("login_password", hash_password("testpass123"))
            clear_login_attempts()

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def test_get_settings_requires_login(self):
        client = self.app.test_client()
        resp = client.get("/api/settings")

        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertEqual(data.get("need_login"), True)
        self.assertEqual((data.get("error") or {}).get("code"), "AUTH_REQUIRED")

    def test_get_settings_exposes_password_change_switch(self):
        client = self.app.test_client()
        self._login(client)

        with patch(
            "outlook_web.controllers.settings.config.get_allow_login_password_change",
            return_value=False,
        ):
            resp = client.get("/api/settings")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        settings = data.get("settings") or {}
        self.assertIn("allow_login_password_change", settings)
        self.assertFalse(settings.get("allow_login_password_change"))

    def test_put_settings_rejects_password_change_when_switch_disabled(self):
        client = self.app.test_client()
        self._login(client)

        with patch(
            "outlook_web.controllers.settings.config.get_allow_login_password_change",
            return_value=False,
        ):
            resp = client.put("/api/settings", json={"login_password": "newpass123"})

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(
            (data.get("error") or {}).get("code"),
            "LOGIN_PASSWORD_CHANGE_DISABLED",
        )

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo
            from outlook_web.security.crypto import verify_password

            stored_password = settings_repo.get_login_password()
            self.assertTrue(verify_password("testpass123", stored_password))
            self.assertFalse(verify_password("newpass123", stored_password))

    def test_put_settings_allows_other_fields_when_switch_disabled(self):
        client = self.app.test_client()
        self._login(client)

        with patch(
            "outlook_web.controllers.settings.config.get_allow_login_password_change",
            return_value=False,
        ):
            resp = client.put("/api/settings", json={"refresh_interval_days": 7})

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))

        resp2 = client.get("/api/settings")
        self.assertEqual(resp2.status_code, 200)
        settings = resp2.get_json().get("settings") or {}
        self.assertEqual(settings.get("refresh_interval_days"), "7")

    def test_put_settings_allows_password_change_when_switch_enabled(self):
        client = self.app.test_client()
        self._login(client)

        with patch(
            "outlook_web.controllers.settings.config.get_allow_login_password_change",
            return_value=True,
        ):
            resp = client.put("/api/settings", json={"login_password": "newpass123"})

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo
            from outlook_web.security.crypto import verify_password

            stored_password = settings_repo.get_login_password()
            self.assertTrue(verify_password("newpass123", stored_password))
            self.assertFalse(verify_password("testpass123", stored_password))
