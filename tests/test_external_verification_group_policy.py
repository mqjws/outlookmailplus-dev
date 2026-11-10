from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class ExternalVerificationGroupPolicyTests(unittest.TestCase):
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
            db.execute("DELETE FROM accounts WHERE email LIKE '%@extapi.test'")
            db.execute("DELETE FROM external_api_keys")
            db.commit()
            settings_repo.set_setting("external_api_key", "abc123")

    def _auth_headers(self):
        return {"X-API-Key": "abc123"}

    def _create_group_with_policy(self, *, length="6-6", regex="", ai_enabled=0, ai_model="") -> int:
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            cols = {str(r["name"]) for r in db.execute("PRAGMA table_info(groups)").fetchall()}
        required = {
            "verification_code_length",
            "verification_code_regex",
            "verification_ai_enabled",
            "verification_ai_model",
        }
        self.assertTrue(required.issubset(cols), f"groups 表缺少策略字段: {sorted(required - cols)}")

        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            name = f"ext_pol_{uuid.uuid4().hex[:8]}"
            db.execute(
                """
                INSERT INTO groups (
                    name, description, color, proxy_url,
                    verification_code_length, verification_code_regex,
                    verification_ai_enabled, verification_ai_model
                ) VALUES (?, '', '#123456', '', ?, ?, ?, ?)
                """,
                (name, length, regex, int(ai_enabled), ai_model),
            )
            db.commit()
            row = db.execute("SELECT id FROM groups WHERE name = ?", (name,)).fetchone()
        return int(row["id"])

    def _insert_outlook_account(self, group_id: int) -> str:
        email_addr = f"{uuid.uuid4().hex}@extapi.test"
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, group_id, status, account_type, provider)
                VALUES (?, 'pw', 'cid-test', 'rt-test', ?, 'active', 'outlook', 'outlook')
                """,
                (email_addr, int(group_id)),
            )
            db.commit()
        return email_addr

    @staticmethod
    def _graph_email(subject="Verification"):
        return {
            "id": "msg-1",
            "subject": subject,
            "from": {"emailAddress": {"address": "noreply@example.com"}},
            "receivedDateTime": "2030-01-01T00:00:00Z",
            "isRead": False,
            "hasAttachments": False,
            "bodyPreview": "preview",
        }

    @staticmethod
    def _graph_detail(body_text: str):
        return {
            "id": "msg-1",
            "subject": "Verification",
            "from": {"emailAddress": {"address": "noreply@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "user@example.com"}}],
            "receivedDateTime": "2030-01-01T00:00:00Z",
            "body": {"content": body_text, "contentType": "text"},
        }

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_extract_uses_group_regex_priority(self, mock_list, mock_detail, mock_raw):
        gid = self._create_group_with_policy(length="6-6", regex=r"\b[A-Z]{4}\d{2}\b")
        email_addr = self._insert_outlook_account(gid)
        mock_list.return_value = {"success": True, "emails": [self._graph_email()]}
        mock_detail.return_value = self._graph_detail("123456 and CODE12")
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        code = (resp.get_json().get("data") or {}).get("verification_code")
        self.assertEqual(code, "CODE12")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_extract_request_override_group(self, mock_list, mock_detail, mock_raw):
        gid = self._create_group_with_policy(length="6-6", regex=r"\b[A-Z]{4}\d{2}\b")
        email_addr = self._insert_outlook_account(gid)
        mock_list.return_value = {"success": True, "emails": [self._graph_email()]}
        mock_detail.return_value = self._graph_detail("target 1234 and CODE12")
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}&code_length=4-4",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        code = (resp.get_json().get("data") or {}).get("verification_code")
        self.assertEqual(code, "1234")

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_extract_group_ai_legacy_fields_do_not_block(self, mock_list):
        gid = self._create_group_with_policy(length="6-6", regex="", ai_enabled=1, ai_model="")
        email_addr = self._insert_outlook_account(gid)
        mock_list.return_value = {"success": True, "emails": [self._graph_email()]}

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}",
            headers=self._auth_headers(),
        )

        # 不再因 group 侧 AI 字段阻断；可能是业务未命中 404 或命中 200
        self.assertIn(resp.status_code, (200, 404))


if __name__ == "__main__":
    unittest.main()
