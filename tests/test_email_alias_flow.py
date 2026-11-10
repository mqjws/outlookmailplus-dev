from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class EmailAliasFlowTests(unittest.TestCase):
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
            db.execute("DELETE FROM accounts WHERE email LIKE '%@aliasflow.test'")
            db.execute("DELETE FROM audit_logs WHERE resource_type = 'external_api'")
            db.commit()
            settings_repo.set_setting("external_api_key", "")

    @staticmethod
    def _utc_iso_now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _graph_email() -> dict:
        return {
            "id": "msg-1",
            "subject": "Your verification code",
            "from": {"emailAddress": {"address": "noreply@example.com"}},
            "receivedDateTime": EmailAliasFlowTests._utc_iso_now(),
            "isRead": False,
            "hasAttachments": False,
            "bodyPreview": "Your code is 123456",
        }

    @staticmethod
    def _graph_detail() -> dict:
        return {
            "id": "msg-1",
            "subject": "Your verification code",
            "from": {"emailAddress": {"address": "noreply@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "user@aliasflow.test"}}],
            "receivedDateTime": EmailAliasFlowTests._utc_iso_now(),
            "body": {"content": "Your code is 123456", "contentType": "text"},
        }

    def _insert_outlook_account(self, email_addr: str) -> None:
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

    def _set_external_api_key(self, value: str):
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
    def test_external_messages_supports_plus_alias_email(self, mock_get_emails_graph):
        self._insert_outlook_account("user@aliasflow.test")
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [self._graph_email()],
        }

        client = self.app.test_client()
        resp = client.get(
            "/api/external/messages",
            query_string={"email": "user+signup@aliasflow.test"},
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_verification_code_supports_plus_alias_email(
        self,
        mock_get_emails_graph,
        mock_get_email_detail_graph,
        mock_get_email_raw_graph,
    ):
        self._insert_outlook_account("user@aliasflow.test")
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [self._graph_email()],
        }
        mock_get_email_detail_graph.return_value = self._graph_detail()
        mock_get_email_raw_graph.return_value = "RAW MIME CONTENT"

        client = self.app.test_client()
        resp = client.get(
            "/api/external/verification-code",
            query_string={"email": "user+signup@aliasflow.test"},
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json().get("data", {}).get("verification_code"), "123456")

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_internal_get_emails_supports_plus_alias_email(self, mock_get_emails_graph):
        self._insert_outlook_account("user@aliasflow.test")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [self._graph_email()],
        }

        client = self.app.test_client()
        self._login(client)
        resp = client.get("/api/emails/user+signup@aliasflow.test")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    @patch("outlook_web.services.graph.get_email_detail_graph")
    def test_internal_get_email_detail_supports_plus_alias_email(self, mock_get_email_detail_graph):
        self._insert_outlook_account("user@aliasflow.test")
        mock_get_email_detail_graph.return_value = self._graph_detail()

        client = self.app.test_client()
        self._login(client)
        resp = client.get("/api/email/user+signup@aliasflow.test/msg-1")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))
