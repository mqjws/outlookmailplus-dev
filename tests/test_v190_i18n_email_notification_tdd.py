"""tests/test_v190_i18n_email_notification_tdd.py — TDD-00010 RED 契约测试

目标：
1. 固定 V1.90 的 settings / error / notification 契约
2. 让当前代码与最新 FD / TD / TDD 的差距直接体现在测试结果里
3. 不用 skip 掩盖未实现项
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from outlook_web.repositories import settings as settings_repo
from outlook_web.security.crypto import encrypt_data
from tests._import_app import clear_login_attempts, import_web_app_module


class V190ApiContractRedTests(unittest.TestCase):
    """TDD-00010 §5 RED 契约测试"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            settings_repo.set_setting("email_notification_enabled", "false")
            settings_repo.set_setting("email_notification_recipient", "")
            settings_repo.set_setting("telegram_bot_token", "")
            settings_repo.set_setting("telegram_chat_id", "")

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        self.assertEqual(payload.get("success"), True)

    def _insert_account(self, email_addr: str) -> int:
        conn = self.module.create_sqlite_connection()
        try:
            cur = conn.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, group_id, remark, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (email_addr, "", "cid_v190", "rt_v190", 1, "", "active"),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def _set_setting(self, key: str, value: str):
        with self.app.app_context():
            settings_repo.set_setting(key, value)

    def test_t_api_001_get_settings_returns_email_notification_fields(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), True)
        settings = data.get("settings") or {}
        self.assertIn("email_notification_enabled", settings)
        self.assertIn("email_notification_recipient", settings)

    def test_t_api_003_enable_notification_requires_recipient_and_message_en(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={
                "email_notification_enabled": True,
                "email_notification_recipient": "",
            },
        )
        self.assertNotEqual(resp.status_code, 404)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "EMAIL_NOTIFICATION_RECIPIENT_REQUIRED")
        self.assertTrue(data["error"].get("message_en"))

    def test_t_api_004_invalid_recipient_returns_stable_error_code(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={
                "email_notification_enabled": False,
                "email_notification_recipient": "not-an-email",
            },
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "EMAIL_NOTIFICATION_RECIPIENT_INVALID")
        self.assertEqual(
            data["error"].get("message_en"),
            "Invalid notification recipient email address",
        )

    def test_t_api_005_enable_notification_requires_email_service(self):
        client = self.app.test_client()
        self._login(client)

        with patch.dict(
            os.environ,
            {
                "EMAIL_NOTIFICATION_SMTP_HOST": "",
                "EMAIL_NOTIFICATION_SMTP_PORT": "",
                "EMAIL_NOTIFICATION_FROM": "",
            },
        ):
            resp = client.put(
                "/api/settings",
                json={
                    "email_notification_enabled": True,
                    "email_notification_recipient": "notify@example.com",
                },
            )

        self.assertEqual(resp.status_code, 503)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "EMAIL_NOTIFICATION_SERVICE_UNAVAILABLE")
        self.assertTrue(data["error"].get("message_en"))

    def test_t_api_005b_save_recipient_success_contains_message_en(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={
                "email_notification_enabled": False,
                "email_notification_recipient": "notify@example.com",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), True)
        self.assertTrue(data.get("message_en"))

    def test_t_api_005c_enable_notification_invalid_smtp_port_returns_precise_error(
        self,
    ):
        client = self.app.test_client()
        self._login(client)

        with patch.dict(
            os.environ,
            {
                "EMAIL_NOTIFICATION_SMTP_HOST": "smtp.example.com",
                "EMAIL_NOTIFICATION_SMTP_PORT": "bad",
                "EMAIL_NOTIFICATION_FROM": "noreply@example.com",
            },
        ):
            resp = client.put(
                "/api/settings",
                json={
                    "email_notification_enabled": True,
                    "email_notification_recipient": "notify@example.com",
                },
            )

        self.assertEqual(resp.status_code, 503)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertEqual(data["error"].get("code"), "EMAIL_NOTIFICATION_SMTP_PORT_INVALID")
        self.assertEqual(data["error"].get("message_en"), "Email notification SMTP port is invalid")

    def test_t_api_005d_enable_notification_invalid_smtp_timeout_returns_precise_error(
        self,
    ):
        client = self.app.test_client()
        self._login(client)

        with patch.dict(
            os.environ,
            {
                "EMAIL_NOTIFICATION_SMTP_HOST": "smtp.example.com",
                "EMAIL_NOTIFICATION_SMTP_PORT": "587",
                "EMAIL_NOTIFICATION_FROM": "noreply@example.com",
                "EMAIL_NOTIFICATION_SMTP_TIMEOUT": "bad",
            },
        ):
            resp = client.put(
                "/api/settings",
                json={
                    "email_notification_enabled": True,
                    "email_notification_recipient": "notify@example.com",
                },
            )

        self.assertEqual(resp.status_code, 503)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertEqual(data["error"].get("code"), "EMAIL_NOTIFICATION_SMTP_TIMEOUT_INVALID")
        self.assertEqual(
            data["error"].get("message_en"),
            "Email notification SMTP timeout is invalid",
        )

    def test_t_api_006_email_test_endpoint_exists_and_requires_saved_recipient(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.post("/api/settings/email-test", json={})
        self.assertNotEqual(
            resp.status_code,
            404,
            "TDD-00010 要求新增 /api/settings/email-test；当前仍返回 404，说明接口尚未实现",
        )
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "EMAIL_NOTIFICATION_RECIPIENT_NOT_CONFIGURED")
        self.assertTrue(data["error"].get("message_en"))

    def test_t_api_007_email_test_success_uses_saved_recipient_and_message_en(self):
        client = self.app.test_client()
        self._login(client)
        self._set_setting("email_notification_recipient", "notify@example.com")

        with (
            patch.dict(
                os.environ,
                {
                    "EMAIL_NOTIFICATION_SMTP_HOST": "smtp.example.com",
                    "EMAIL_NOTIFICATION_SMTP_PORT": "587",
                    "EMAIL_NOTIFICATION_FROM": "noreply@example.com",
                },
            ),
            patch("smtplib.SMTP") as smtp_mock,
        ):
            resp = client.post("/api/settings/email-test", json={})

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), True)
        self.assertEqual(data.get("message"), "测试邮件已提交，请检查收件箱")
        self.assertEqual(data.get("message_en"), "Test email accepted. Please check your inbox")
        smtp_mock.return_value.__enter__.return_value.send_message.assert_called_once()

    def test_t_api_007b_email_test_unavailable_returns_structured_error(self):
        client = self.app.test_client()
        self._login(client)
        self._set_setting("email_notification_recipient", "notify@example.com")

        with patch.dict(
            os.environ,
            {
                "EMAIL_NOTIFICATION_SMTP_HOST": "",
                "EMAIL_NOTIFICATION_SMTP_PORT": "",
                "EMAIL_NOTIFICATION_FROM": "",
            },
        ):
            resp = client.post("/api/settings/email-test", json={})

        self.assertEqual(resp.status_code, 503)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "EMAIL_NOTIFICATION_SERVICE_UNAVAILABLE")
        self.assertTrue(data["error"].get("message_en"))

    def test_t_api_007c_email_test_invalid_smtp_port_returns_stable_error(self):
        client = self.app.test_client()
        self._login(client)
        self._set_setting("email_notification_recipient", "notify@example.com")

        with patch.dict(
            os.environ,
            {
                "EMAIL_NOTIFICATION_SMTP_HOST": "smtp.example.com",
                "EMAIL_NOTIFICATION_SMTP_PORT": "invalid",
                "EMAIL_NOTIFICATION_FROM": "noreply@example.com",
            },
        ):
            resp = client.post("/api/settings/email-test", json={})

        self.assertEqual(resp.status_code, 503)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertEqual(data["error"].get("code"), "EMAIL_NOTIFICATION_SMTP_PORT_INVALID")
        self.assertEqual(data["error"].get("message_en"), "Email notification SMTP port is invalid")

    def test_t_api_007d_email_test_invalid_timeout_returns_stable_error(self):
        client = self.app.test_client()
        self._login(client)
        self._set_setting("email_notification_recipient", "notify@example.com")

        with patch.dict(
            os.environ,
            {
                "EMAIL_NOTIFICATION_SMTP_HOST": "smtp.example.com",
                "EMAIL_NOTIFICATION_SMTP_PORT": "587",
                "EMAIL_NOTIFICATION_FROM": "noreply@example.com",
                "EMAIL_NOTIFICATION_SMTP_TIMEOUT": "bad",
            },
        ):
            resp = client.post("/api/settings/email-test", json={})

        self.assertEqual(resp.status_code, 503)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertEqual(data["error"].get("code"), "EMAIL_NOTIFICATION_SMTP_TIMEOUT_INVALID")
        self.assertEqual(
            data["error"].get("message_en"),
            "Email notification SMTP timeout is invalid",
        )

    def test_t_api_007e_email_test_rejects_invalid_saved_recipient(self):
        client = self.app.test_client()
        self._login(client)
        self._set_setting("email_notification_recipient", "bad-recipient")

        with patch.dict(
            os.environ,
            {
                "EMAIL_NOTIFICATION_SMTP_HOST": "smtp.example.com",
                "EMAIL_NOTIFICATION_SMTP_PORT": "587",
                "EMAIL_NOTIFICATION_FROM": "noreply@example.com",
            },
        ):
            resp = client.post("/api/settings/email-test", json={})

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertEqual(data["error"].get("code"), "EMAIL_NOTIFICATION_RECIPIENT_INVALID")
        self.assertEqual(
            data["error"].get("message_en"),
            "Invalid notification recipient email address",
        )

    def test_t_api_008_login_invalid_password_contains_message_en(self):
        client = self.app.test_client()

        resp = client.post("/login", json={"password": "wrong_password"})
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "LOGIN_INVALID_PASSWORD")
        self.assertTrue(data["error"].get("message_en"))

    def test_t_api_009_invalid_cron_contains_message_en(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.post("/api/settings/validate-cron", json={"cron_expression": "invalid cron expr"})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "CRON_EXPRESSION_INVALID")
        self.assertTrue(data["error"].get("message_en"))

    def test_t_api_009b_telegram_test_not_configured_returns_structured_error(self):
        client = self.app.test_client()
        self._login(client)
        self._set_setting("telegram_bot_token", "")
        self._set_setting("telegram_chat_id", "")

        resp = client.post("/api/settings/telegram-test", json={})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "TELEGRAM_NOT_CONFIGURED")
        self.assertTrue(data["error"].get("message_en"))

    def test_t_api_009c_telegram_test_success_contains_message_en(self):
        client = self.app.test_client()
        self._login(client)
        self._set_setting("telegram_bot_token", encrypt_data("bot_token_value"))
        self._set_setting("telegram_chat_id", "123456")

        with patch(
            "outlook_web.services.telegram_push._send_telegram_message",
            return_value=True,
        ):
            resp = client.post("/api/settings/telegram-test", json={})

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), True)
        self.assertTrue(data.get("message_en"))

    def test_t_api_009d_telegram_test_failure_contains_message_en(self):
        client = self.app.test_client()
        self._login(client)
        self._set_setting("telegram_bot_token", encrypt_data("bot_token_value"))
        self._set_setting("telegram_chat_id", "123456")

        with patch(
            "outlook_web.services.telegram_push._send_telegram_message",
            return_value=False,
        ):
            resp = client.post("/api/settings/telegram-test", json={})

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "TELEGRAM_TEST_SEND_FAILED")
        self.assertTrue(data["error"].get("message_en"))

    def test_t_api_010_telegram_toggle_success_contains_message_en(self):
        client = self.app.test_client()
        self._login(client)
        account_id = self._insert_account("v190_toggle@example.com")

        resp = client.post(f"/api/accounts/{account_id}/telegram-toggle", json={"enabled": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), True)
        self.assertTrue(data.get("message_en"))

    def test_t_api_013_telegram_toggle_account_not_found_returns_message_en(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.post("/api/accounts/999999/telegram-toggle", json={"enabled": True})
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "ACCOUNT_NOT_FOUND")
        self.assertTrue(data["error"].get("message_en"))


class V190NotificationSchemaRedTests(unittest.TestCase):
    """TDD-00010 §6 RED 数据模型测试"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def test_schema_version_upgraded_to_15(self):
        """TDD-00010 §6：schema 已包含 v15 变更（version >= 15 即满足，当前允许继续升级）"""
        from outlook_web.db import DB_SCHEMA_VERSION

        conn = self.module.create_sqlite_connection()
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = 'db_schema_version'").fetchone()
            self.assertIsNotNone(row)
            self.assertGreaterEqual(
                int(row[0]),
                15,
                f"schema 版本应 >= 15，当前 DB_SCHEMA_VERSION={DB_SCHEMA_VERSION}",
            )
        finally:
            conn.close()

    def test_notification_cursor_states_table_exists(self):
        conn = self.module.create_sqlite_connection()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'notification_cursor_states'"
            ).fetchone()
            self.assertIsNotNone(row, "TDD-00010 / TD-00010 要求新增 notification_cursor_states 表")
        finally:
            conn.close()

    def test_notification_delivery_logs_table_exists(self):
        conn = self.module.create_sqlite_connection()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'notification_delivery_logs'"
            ).fetchone()
            self.assertIsNotNone(row, "TDD-00010 / TD-00010 要求新增 notification_delivery_logs 表")
        finally:
            conn.close()

    def test_notification_delivery_logs_has_expected_unique_key(self):
        conn = self.module.create_sqlite_connection()
        try:
            table_sql_row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'notification_delivery_logs'"
            ).fetchone()
            self.assertIsNotNone(table_sql_row, "notification_delivery_logs 表必须存在后才能校验唯一键")
            table_sql = table_sql_row[0] or ""
            self.assertIn("UNIQUE(channel, source_type, source_key, message_id)", table_sql)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
