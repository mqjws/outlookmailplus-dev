from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class EmailAliasMigrationCompatTests(unittest.TestCase):
    """验证邮箱别名能力上线后，用户正常使用可无缝迁移。"""

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
            db.execute("DELETE FROM accounts WHERE email LIKE '%@aliascompat.test'")
            db.execute("DELETE FROM audit_logs WHERE resource_type = 'external_api'")
            db.commit()

            settings_repo.set_setting("external_api_key", "")

    @staticmethod
    def _utc_iso_now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _graph_email(message_id: str = "msg-1") -> dict:
        return {
            "id": message_id,
            "subject": "Your verification code",
            "from": {"emailAddress": {"address": "noreply@example.com"}},
            "receivedDateTime": EmailAliasMigrationCompatTests._utc_iso_now(),
            "isRead": False,
            "hasAttachments": False,
            "bodyPreview": "Your code is 123456",
        }

    @staticmethod
    def _graph_detail(message_id: str = "msg-1") -> dict:
        return {
            "id": message_id,
            "subject": "Your verification code",
            "from": {"emailAddress": {"address": "noreply@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "user@aliascompat.test"}}],
            "receivedDateTime": EmailAliasMigrationCompatTests._utc_iso_now(),
            "body": {"content": "Your code is 123456", "contentType": "text"},
        }

    def _insert_outlook_account(self, email_addr: str = "user@aliascompat.test") -> str:
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, group_id, status, account_type, provider)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_addr,
                    "pw",
                    "cid-test",
                    "rt-test",
                    1,
                    "active",
                    "outlook",
                    "outlook",
                ),
            )
            db.commit()
        return email_addr

    def _set_external_api_key(self, value: str = "abc123"):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_key", value)

    @staticmethod
    def _auth_headers(value: str = "abc123"):
        return {"X-API-Key": value}

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_messages_alias_and_canonical_are_equivalent(self, mock_get_emails_graph):
        canonical_email = self._insert_outlook_account()
        alias_email = "user+signup@aliascompat.test"
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [self._graph_email("msg-1")],
        }

        client = self.app.test_client()

        resp_canonical = client.get(
            "/api/external/messages",
            query_string={"email": canonical_email},
            headers=self._auth_headers(),
        )
        resp_alias = client.get(
            "/api/external/messages",
            query_string={"email": alias_email},
            headers=self._auth_headers(),
        )

        self.assertEqual(resp_canonical.status_code, 200)
        self.assertEqual(resp_alias.status_code, 200)

        data_canonical = resp_canonical.get_json().get("data", {})
        data_alias = resp_alias.get_json().get("data", {})
        self.assertEqual(data_canonical.get("count"), data_alias.get("count"))
        self.assertEqual(
            (data_canonical.get("emails") or [])[0].get("id"),
            (data_alias.get("emails") or [])[0].get("id"),
        )

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_verification_code_alias_and_canonical_are_equivalent(
        self,
        mock_get_emails_graph,
        mock_get_email_detail_graph,
        mock_get_email_raw_graph,
    ):
        canonical_email = self._insert_outlook_account()
        alias_email = "user+signup@aliascompat.test"
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [self._graph_email("msg-1")],
        }
        mock_get_email_detail_graph.return_value = self._graph_detail("msg-1")
        mock_get_email_raw_graph.return_value = "RAW MIME CONTENT"

        client = self.app.test_client()

        resp_canonical = client.get(
            "/api/external/verification-code",
            query_string={"email": canonical_email},
            headers=self._auth_headers(),
        )
        resp_alias = client.get(
            "/api/external/verification-code",
            query_string={"email": alias_email},
            headers=self._auth_headers(),
        )

        self.assertEqual(resp_canonical.status_code, 200)
        self.assertEqual(resp_alias.status_code, 200)

        data_canonical = resp_canonical.get_json().get("data", {})
        data_alias = resp_alias.get_json().get("data", {})
        self.assertEqual(data_canonical.get("verification_code"), data_alias.get("verification_code"))
        self.assertEqual(data_alias.get("verification_code"), "123456")

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_internal_get_emails_alias_and_canonical_are_equivalent(self, mock_get_emails_graph):
        canonical_email = self._insert_outlook_account()
        alias_email = "user+signup@aliascompat.test"
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [self._graph_email("msg-1")],
        }

        client = self.app.test_client()
        self._login(client)

        resp_canonical = client.get(f"/api/emails/{canonical_email}")
        resp_alias = client.get(f"/api/emails/{alias_email}")

        self.assertEqual(resp_canonical.status_code, 200)
        self.assertEqual(resp_alias.status_code, 200)

        data_canonical = resp_canonical.get_json()
        data_alias = resp_alias.get_json()
        self.assertTrue(data_canonical.get("success"))
        self.assertTrue(data_alias.get("success"))
        self.assertEqual(
            (data_canonical.get("emails") or [])[0].get("id"),
            (data_alias.get("emails") or [])[0].get("id"),
        )
