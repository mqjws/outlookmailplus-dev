from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class EmailCredentialDecryptErrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)

    def _db(self):
        return self.module.create_sqlite_connection()

    def test_get_emails_returns_explicit_error_when_account_credentials_cannot_be_decrypted(self):
        unique = uuid.uuid4().hex
        email_addr = f"decrypt_fail_{unique}@example.com"

        conn = self._db()
        try:
            conn.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, group_id, remark, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_addr,
                    "enc:not-a-valid-token",
                    f"cid_{unique}",
                    "enc:not-a-valid-token",
                    1,
                    "",
                    "active",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        client = self.app.test_client()
        self._login(client)

        with patch("outlook_web.services.graph.get_emails_graph") as mock_graph:
            resp = client.get(f"/api/emails/{email_addr}?folder=inbox&skip=0&top=10")

        self.assertEqual(resp.status_code, 500)
        data = resp.get_json() or {}
        self.assertEqual(data.get("code"), "ACCOUNT_CREDENTIAL_DECRYPT_FAILED")
        self.assertIn("fields", data.get("details", {}))
        self.assertIn("refresh_token", data.get("details", {}).get("fields", []))
        mock_graph.assert_not_called()

    def test_extract_verification_returns_same_decrypt_error_and_stops_before_remote_fetch(self):
        unique = uuid.uuid4().hex
        email_addr = f"decrypt_extract_{unique}@example.com"

        conn = self._db()
        try:
            conn.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, group_id, remark, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_addr,
                    "enc:not-a-valid-token",
                    f"cid_{unique}",
                    "enc:not-a-valid-token",
                    1,
                    "",
                    "active",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        client = self.app.test_client()
        self._login(client)

        with patch("outlook_web.services.graph.get_emails_graph") as mock_graph:
            resp = client.get(f"/api/emails/{email_addr}/extract-verification")

        self.assertEqual(resp.status_code, 500)
        data = resp.get_json() or {}
        self.assertEqual(data.get("code"), "ACCOUNT_CREDENTIAL_DECRYPT_FAILED")
        self.assertIn("refresh_token", data.get("details", {}).get("fields", []))
        mock_graph.assert_not_called()
