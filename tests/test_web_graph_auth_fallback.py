from __future__ import annotations

import unittest
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class WebGraphAuthFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
        from outlook_web.services.channel_capability_cache import clear_all

        clear_all()

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def _insert_outlook_account(self, email_addr: str):
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (
                    email, password, client_id, refresh_token,
                    group_id, status, account_type, provider
                ) VALUES (?, 'pw', 'cid-test', 'rt-test', 1, 'active', 'outlook', 'outlook')
                """,
                (email_addr,),
            )
            db.commit()

    @patch("outlook_web.services.imap.get_emails_imap_concurrent")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_get_emails_graph_401_still_fallback_to_imap(
        self,
        mock_graph_list,
        mock_imap_concurrent,
    ):
        email_addr = "fallback_read@example.com"
        self._insert_outlook_account(email_addr)

        mock_graph_list.return_value = {
            "success": False,
            "auth_expired": True,
            "error": {
                "code": "EMAIL_FETCH_FAILED",
                "type": "GraphAPIError",
                "status": 401,
                "message": "graph unauthorized",
            },
        }
        mock_imap_concurrent.return_value = {
            "success": True,
            "server": "outlook.live.com",
            "emails": [
                {
                    "id": "imap-msg-1",
                    "subject": "via imap",
                    "from": "noreply@example.com",
                    "date": "2030-01-01T00:00:00Z",
                    "is_read": False,
                    "has_attachments": False,
                    "body_preview": "hello",
                }
            ],
        }

        client = self.app.test_client()
        self._login(client)
        resp = client.get(f"/api/emails/{email_addr}?folder=inbox&skip=0&top=20")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("method"), "IMAP (New)")
        self.assertTrue(mock_imap_concurrent.called)

    @patch("outlook_web.services.imap.get_emails_imap_concurrent")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_get_emails_returns_auth_expired_only_after_all_fallbacks_fail(
        self,
        mock_graph_list,
        mock_imap_concurrent,
    ):
        email_addr = "fallback_fail@example.com"
        self._insert_outlook_account(email_addr)

        mock_graph_list.return_value = {
            "success": False,
            "auth_expired": True,
            "error": {
                "code": "EMAIL_FETCH_FAILED",
                "type": "GraphAPIError",
                "status": 401,
                "message": "graph unauthorized",
            },
        }
        mock_imap_concurrent.return_value = {
            "success": False,
            "error": {"code": "IMAP_AUTH_FAILED", "message": "all imap fail"},
            "server_errors": {
                "outlook.live.com": {"code": "IMAP_AUTH_FAILED", "message": "new fail"},
                "outlook.office365.com": {"code": "IMAP_AUTH_FAILED", "message": "old fail"},
            },
        }

        client = self.app.test_client()
        self._login(client)
        resp = client.get(f"/api/emails/{email_addr}?folder=inbox&skip=0&top=20")

        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("error", {}).get("code"), "ACCOUNT_AUTH_EXPIRED")
        self.assertEqual(mock_imap_concurrent.call_count, 1)

    @patch("outlook_web.services.imap.get_emails_imap_concurrent")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_get_emails_skips_cached_unavailable_graph_after_imap_success(
        self,
        mock_graph_list,
        mock_imap_concurrent,
    ):
        email_addr = "cached_imap_read@example.com"
        self._insert_outlook_account(email_addr)

        mock_graph_list.return_value = {
            "success": False,
            "auth_expired": False,
            "error": {"code": "GRAPH_TOKEN_FAILED", "message": "AADSTS90023"},
        }
        mock_imap_concurrent.return_value = {
            "success": True,
            "server": "outlook.live.com",
            "emails": [
                {
                    "id": "imap-msg-1",
                    "subject": "via imap",
                    "from": "noreply@example.com",
                    "date": "2030-01-01T00:00:00Z",
                    "is_read": False,
                    "has_attachments": False,
                    "body_preview": "hello",
                }
            ],
        }

        client = self.app.test_client()
        self._login(client)

        first = client.get(f"/api/emails/{email_addr}?folder=inbox&skip=0&top=20")
        second = client.get(f"/api/emails/{email_addr}?folder=inbox&skip=0&top=20")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.get_json().get("method"), "IMAP (New)")
        self.assertEqual(second.get_json().get("method"), "IMAP (New)")
        self.assertEqual(mock_graph_list.call_count, 1)
        self.assertEqual(mock_imap_concurrent.call_count, 2)


if __name__ == "__main__":
    unittest.main()
