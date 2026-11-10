import unittest
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class OutlookBasicAuthRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)

    def _set_external_api_key(self, value: str):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_key", value)

    @staticmethod
    def _auth_headers(value: str = "abc123"):
        return {"X-API-Key": value}

    def _insert_imap_outlook_account(self, email_addr: str) -> int:
        conn = self.module.create_sqlite_connection()
        try:
            cur = conn.execute(
                """
                INSERT INTO accounts (
                    email, password, client_id, refresh_token, account_type, provider,
                    imap_host, imap_port, imap_password, group_id, remark, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_addr,
                    "",
                    "",
                    "",
                    "imap",
                    "outlook",
                    "outlook.live.com",
                    993,
                    "enc:dummy",
                    1,
                    "",
                    "active",
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def test_email_detail_endpoint_returns_explicit_basic_auth_blocked_message(self):
        client = self.app.test_client()
        self._login(client)
        email_addr = "legacy-detail@outlook.com"
        self._insert_imap_outlook_account(email_addr)

        error_payload = {
            "code": "IMAP_AUTH_FAILED",
            "message": "IMAP 认证失败：Outlook.com 已阻止 Basic Auth（账号密码直连），请改用 Outlook OAuth 导入（client_id + refresh_token）",
            "message_en": "IMAP authentication failed: Outlook.com blocked Basic Auth. Use Outlook OAuth import instead.",
            "type": "IMAPAuthError",
            "status": 401,
            "details": "",
            "trace_id": "test-trace",
        }

        with patch(
            "outlook_web.controllers.emails.get_email_detail_imap_generic_result",
            return_value={"success": False, "error": error_payload, "error_code": "IMAP_AUTH_FAILED"},
        ):
            resp = client.get(f"/api/email/{email_addr}/message-1")

        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data["error"]["code"], "IMAP_AUTH_FAILED")
        self.assertIn("Outlook.com 已阻止 Basic Auth", data["error"]["message"])

    def test_external_api_imap_detail_surfaces_explicit_basic_auth_blocked_message(self):
        email_addr = "legacy-external@outlook.com"
        with self.app.app_context():
            self._insert_imap_outlook_account(email_addr)
            from outlook_web.services import external_api as external_api_service

            error_payload = {
                "code": "IMAP_AUTH_FAILED",
                "message": "IMAP 认证失败：Outlook.com 已阻止 Basic Auth（账号密码直连），请改用 Outlook OAuth 导入（client_id + refresh_token）",
                "message_en": "IMAP authentication failed: Outlook.com blocked Basic Auth. Use Outlook OAuth import instead.",
                "type": "IMAPAuthError",
                "status": 401,
                "details": "",
                "trace_id": "test-trace",
            }

            with patch(
                "outlook_web.services.external_api.get_email_detail_imap_generic_result",
                return_value={"success": False, "error": error_payload, "error_code": "IMAP_AUTH_FAILED"},
            ):
                with self.assertRaises(external_api_service.UpstreamReadFailedError) as ctx:
                    external_api_service.get_message_detail_for_external(email_addr=email_addr, message_id="mid-1")

        self.assertIn("Outlook.com 已阻止 Basic Auth", str(ctx.exception))
        self.assertEqual(ctx.exception.data["code"], "IMAP_AUTH_FAILED")

    def test_extract_verification_endpoint_preserves_imap_auth_error_from_list_step(self):
        client = self.app.test_client()
        self._login(client)
        email_addr = "legacy-extract@outlook.com"
        self._insert_imap_outlook_account(email_addr)

        error_payload = {
            "code": "IMAP_AUTH_FAILED",
            "message": "IMAP 认证失败：Outlook.com 已阻止 Basic Auth（账号密码直连），请改用 Outlook OAuth 导入（client_id + refresh_token）",
            "message_en": "IMAP authentication failed: Outlook.com blocked Basic Auth. Use Outlook OAuth import instead.",
            "type": "IMAPAuthError",
            "status": 401,
            "details": "",
            "trace_id": "test-trace",
        }

        with patch(
            "outlook_web.controllers.emails.get_emails_imap_generic",
            return_value={"success": False, "error": error_payload, "error_code": "IMAP_AUTH_FAILED"},
        ):
            resp = client.get(f"/api/emails/{email_addr}/extract-verification")

        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data["code"], "IMAP_AUTH_FAILED")
        self.assertEqual(data["error"]["code"], "IMAP_AUTH_FAILED")
        self.assertIn("Outlook.com 已阻止 Basic Auth", data["error"]["message"])

    def test_external_api_http_detail_preserves_imap_auth_failed_top_level_code(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        email_addr = "legacy-http-detail@outlook.com"
        self._insert_imap_outlook_account(email_addr)

        error_payload = {
            "code": "IMAP_AUTH_FAILED",
            "message": "IMAP 认证失败：Outlook.com 已阻止 Basic Auth（账号密码直连），请改用 Outlook OAuth 导入（client_id + refresh_token）",
            "message_en": "IMAP authentication failed: Outlook.com blocked Basic Auth. Use Outlook OAuth import instead.",
            "type": "IMAPAuthError",
            "status": 401,
            "details": "",
            "trace_id": "test-trace",
        }

        with patch(
            "outlook_web.services.external_api.get_email_detail_imap_generic_result",
            return_value={"success": False, "error": error_payload, "error_code": "IMAP_AUTH_FAILED"},
        ):
            resp = client.get(
                f"/api/external/messages/msg-1?email={email_addr}",
                headers=self._auth_headers(),
            )

        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data["code"], "IMAP_AUTH_FAILED")
        self.assertIn("Outlook.com 已阻止 Basic Auth", data["message"])

    def test_external_api_http_raw_preserves_imap_auth_failed_top_level_code(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        email_addr = "legacy-http-raw@outlook.com"
        self._insert_imap_outlook_account(email_addr)

        error_payload = {
            "code": "IMAP_AUTH_FAILED",
            "message": "IMAP 认证失败：Outlook.com 已阻止 Basic Auth（账号密码直连），请改用 Outlook OAuth 导入（client_id + refresh_token）",
            "message_en": "IMAP authentication failed: Outlook.com blocked Basic Auth. Use Outlook OAuth import instead.",
            "type": "IMAPAuthError",
            "status": 401,
            "details": "",
            "trace_id": "test-trace",
        }

        with patch(
            "outlook_web.services.external_api.get_email_detail_imap_generic_result",
            return_value={"success": False, "error": error_payload, "error_code": "IMAP_AUTH_FAILED"},
        ):
            resp = client.get(
                f"/api/external/messages/msg-1/raw?email={email_addr}",
                headers=self._auth_headers(),
            )

        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data["code"], "IMAP_AUTH_FAILED")
        self.assertIn("Outlook.com 已阻止 Basic Auth", data["message"])
