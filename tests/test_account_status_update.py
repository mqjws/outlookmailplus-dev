import unittest

from tests._import_app import clear_login_attempts, import_web_app_module


class AccountStatusUpdateTests(unittest.TestCase):
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
        self.assertTrue(resp.get_json().get("success"))

    def _insert_account(self, email_addr: str = "status-update@test.example") -> int:
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            cur = db.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, group_id, status, account_type, provider)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (email_addr, "pw", "cid-test", "rt-test", 1, "active", "outlook", "outlook"),
            )
            db.commit()
            return int(cur.lastrowid)

    def test_update_account_status_rejects_invalid_status(self):
        client = self.app.test_client()
        self._login(client)
        account_id = self._insert_account()

        resp = client.put(f"/api/accounts/{account_id}", json={"status": "paused"})

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"]["code"], "INVALID_PARAM")

    def test_update_account_status_returns_404_for_missing_account(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put("/api/accounts/999999", json={"status": "inactive"})

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["error"]["code"], "ACCOUNT_NOT_FOUND")
