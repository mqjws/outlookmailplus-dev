import unittest
import uuid
from typing import Optional

from werkzeug.exceptions import BadRequest

from tests._import_app import clear_login_attempts, import_web_app_module

try:
    from flask_wtf.csrf import CSRFError
except ImportError:  # pragma: no cover
    CSRFError = None  # type: ignore


class CsrfRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        self._original_csrf_enabled = self.app.config.get("WTF_CSRF_ENABLED")
        self._original_csrf_check_default = self.app.config.get("WTF_CSRF_CHECK_DEFAULT")
        self.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=True,
            WTF_CSRF_CHECK_DEFAULT=True,
        )

        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db

            db = get_db()
            db.execute("DELETE FROM accounts WHERE email LIKE '%@csrf.test'")
            db.commit()

    def tearDown(self):
        self.app.config.update(
            WTF_CSRF_ENABLED=self._original_csrf_enabled,
            WTF_CSRF_CHECK_DEFAULT=self._original_csrf_check_default,
        )

    def _login(self, client):
        response = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(response.status_code, 200)

    def _default_group_id(self) -> int:
        with self.app.app_context():
            from outlook_web.repositories import groups as groups_repo

            return int(groups_repo.get_default_group_id())

    def _account_payload(self, email_addr: Optional[str] = None) -> dict:
        unique = uuid.uuid4().hex[:10]
        return {
            "account_string": f"{email_addr or f'csrf_{unique}@csrf.test'}----pwd----cid_{unique}----rt_{unique}",
            "group_id": self._default_group_id(),
        }

    def _get_csrf_token(self, client) -> str:
        response = client.get("/api/csrf-token")
        self.assertEqual(response.status_code, 200)
        token = response.get_json().get("csrf_token")
        self.assertTrue(token)
        return token

    def test_post_accounts_without_csrf_token_is_rejected(self):
        client = self.app.test_client()
        self._login(client)

        response = client.post("/api/accounts", json=self._account_payload())

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data["error"].get("code"), "CSRF_TOKEN_INVALID")
        self.assertEqual(data["error"].get("type"), "CSRFError")
        self.assertEqual(data["error"].get("message"), "会话已失效，请刷新页面后重试")
        self.assertIn("csrf", (data["error"].get("details") or "").lower())

    def test_get_csrf_token_then_post_accounts_succeeds(self):
        client = self.app.test_client()
        self._login(client)
        csrf_token = self._get_csrf_token(client)

        response = client.post(
            "/api/accounts",
            json=self._account_payload(),
            headers={"X-CSRFToken": csrf_token},
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["summary"].get("imported"), 1)
        self.assertEqual(data["summary"].get("failed"), 0)

    def test_token_from_other_session_returns_explicit_csrf_error(self):
        client_a = self.app.test_client()
        self._login(client_a)
        csrf_token_a = self._get_csrf_token(client_a)

        client_b = self.app.test_client()
        self._login(client_b)

        response = client_b.post(
            "/api/accounts",
            json=self._account_payload(),
            headers={"X-CSRFToken": csrf_token_a},
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data["error"].get("code"), "CSRF_TOKEN_INVALID")
        self.assertEqual(data["error"].get("message"), "会话已失效，请刷新页面后重试")
        self.assertIn("The CSRF session token is missing", data["error"].get("details") or "")

    def test_other_protected_endpoint_still_requires_valid_csrf_token(self):
        client = self.app.test_client()
        self._login(client)

        payload = {"external_api_public_mode": False}
        rejected_response = client.put("/api/settings", json=payload)
        self.assertEqual(rejected_response.status_code, 400)
        rejected_data = rejected_response.get_json()
        self.assertEqual(rejected_data["error"].get("code"), "CSRF_TOKEN_INVALID")

        csrf_token = self._get_csrf_token(client)
        success_response = client.put(
            "/api/settings",
            json=payload,
            headers={"X-CSRFToken": csrf_token},
        )
        self.assertEqual(success_response.status_code, 200)
        success_data = success_response.get_json()
        self.assertTrue(success_data.get("success"))

    def test_plain_bad_request_with_csrf_text_is_not_mapped_as_csrf_error(self):
        from outlook_web.middleware.error_handler import handle_http_exception

        with self.app.test_request_context("/api/test-bad-request"):
            response, status_code = handle_http_exception(BadRequest("business error mentions csrf field name"))

        self.assertEqual(status_code, 400)
        data = response.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data["error"].get("code"), "HTTP_ERROR")
        self.assertEqual(data["error"].get("type"), "HttpError")

    @unittest.skipIf(CSRFError is None, "flask-wtf unavailable")
    def test_explicit_csrf_exception_is_mapped_to_csrf_error_code(self):
        from outlook_web.middleware.error_handler import handle_http_exception

        with self.app.test_request_context("/api/test-csrf"):
            response, status_code = handle_http_exception(CSRFError("The CSRF token is invalid."))

        self.assertEqual(status_code, 400)
        data = response.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data["error"].get("code"), "CSRF_TOKEN_INVALID")
        self.assertEqual(data["error"].get("type"), "CSRFError")


if __name__ == "__main__":
    unittest.main()
