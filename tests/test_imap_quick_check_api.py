from __future__ import annotations

import unittest
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class ImapQuickCheckApiTests(unittest.TestCase):
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

    def _insert_outlook_account(self, email_addr: str) -> int:
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            cursor = db.execute(
                """
                INSERT INTO accounts (
                    email, password, client_id, refresh_token,
                    group_id, status, account_type, provider
                ) VALUES (?, 'pw', 'cid-test', 'rt-test', 1, 'active', 'outlook', 'outlook')
                """,
                (email_addr,),
            )
            db.commit()
            return int(cursor.lastrowid)

    @patch("outlook_web.services.graph.get_emails_graph")
    @patch("outlook_web.services.imap.check_imap_availability_concurrent")
    def test_quick_check_success_records_preferred_imap_channel(self, mock_quick_check, mock_graph):
        email_addr = "quick-ok@example.com"
        account_id = self._insert_outlook_account(email_addr)
        mock_graph.return_value = {"success": False, "error": {"code": "GRAPH_FAILED"}}
        mock_quick_check.side_effect = [
            {
                "success": False,
                "error": {"code": "IMAP_NEW_FAILED"},
            },
            {
                "success": True,
                "server": "outlook.office365.com",
                "selected_folder": "INBOX",
                "elapsed_ms": 123,
                "token_elapsed_ms": 25,
            },
        ]

        client = self.app.test_client()
        self._login(client)
        resp = client.post("/api/emails/quick-check", json={"account_ids": [account_id]})

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("summary", {}).get("success_accounts"), 1)
        result = data.get("results", [])[0]
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("channel"), "imap_old")
        self.assertEqual(result.get("method"), "IMAP (Old)")
        self.assertNotIn("new_refresh_token", result)

        with self.app.app_context():
            from outlook_web.repositories.accounts import get_preferred_verification_channel

            self.assertEqual(get_preferred_verification_channel(account_id), "imap_old")

    @patch("outlook_web.services.graph.get_emails_graph")
    @patch("outlook_web.services.imap.check_imap_availability_concurrent")
    def test_quick_check_graph_success_records_preferred_graph_channel(self, mock_quick_check, mock_graph):
        email_addr = "quick-graph-ok@example.com"
        account_id = self._insert_outlook_account(email_addr)
        mock_graph.return_value = {
            "success": True,
            "emails": [],
            "new_refresh_token": "rt-new",
        }

        client = self.app.test_client()
        self._login(client)
        resp = client.post("/api/emails/quick-check", json={"account_ids": [account_id]})

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("summary", {}).get("success_accounts"), 1)
        result = data.get("results", [])[0]
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("channel"), "graph_inbox")
        self.assertEqual(result.get("method"), "Graph API (Inbox)")
        self.assertNotIn("new_refresh_token", result)
        mock_quick_check.assert_not_called()

        with self.app.app_context():
            from outlook_web.repositories.accounts import get_preferred_verification_channel

            self.assertEqual(get_preferred_verification_channel(account_id), "graph_inbox")

    @patch("outlook_web.services.graph.get_emails_graph")
    @patch("outlook_web.services.imap.check_imap_availability_concurrent")
    def test_quick_check_failure_returns_per_account_error(self, mock_quick_check, mock_graph):
        email_addr = "quick-fail@example.com"
        account_id = self._insert_outlook_account(email_addr)
        mock_graph.return_value = {"success": False, "error": {"code": "GRAPH_FAILED"}}
        mock_quick_check.side_effect = [
            {
                "success": False,
                "error": {"code": "IMAP_AUTH_FAILED"},
            },
            {
                "success": False,
                "error": {"code": "IMAP_AUTH_FAILED"},
            },
        ]

        client = self.app.test_client()
        self._login(client)
        resp = client.post("/api/emails/quick-check", json={"account_ids": [account_id]})

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("summary", {}).get("failed_accounts"), 1)
        result = data.get("results", [])[0]
        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("error", {}).get("code"), "MAILBOX_QUICK_CHECK_FAILED")
        self.assertEqual(
            set((result.get("channel_errors") or {}).keys()),
            {"graph_inbox", "graph_junk", "imap_new", "imap_old"},
        )


if __name__ == "__main__":
    unittest.main()
