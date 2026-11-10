import unittest
import uuid

from tests._import_app import clear_login_attempts, import_web_app_module


class PoolRegistrationTests(unittest.TestCase):
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

    def _account_row(self, email_addr: str):
        conn = self.module.create_sqlite_connection()
        try:
            return conn.execute(
                "SELECT email, pool_status, provider, account_type FROM accounts WHERE email = ? LIMIT 1",
                (email_addr,),
            ).fetchone()
        finally:
            conn.close()

    def test_standard_import_keeps_account_outside_pool_by_default(self):
        client = self.app.test_client()
        self._login(client)

        email_addr = f"default_pool_{uuid.uuid4().hex}@poolreg.test"
        resp = client.post(
            "/api/accounts",
            json={
                "account_string": f"{email_addr}----pwd----cid----rtoken",
                "group_id": 1,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))

        row = self._account_row(email_addr)
        self.assertIsNotNone(row)
        self.assertIsNone(row["pool_status"])

    def test_standard_import_can_explicitly_join_pool(self):
        client = self.app.test_client()
        self._login(client)

        email_addr = f"join_pool_{uuid.uuid4().hex}@poolreg.test"
        resp = client.post(
            "/api/accounts",
            json={
                "account_string": f"{email_addr}----pwd----cid----rtoken",
                "group_id": 1,
                "add_to_pool": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))

        row = self._account_row(email_addr)
        self.assertIsNotNone(row)
        self.assertEqual(row["pool_status"], "available")
        self.assertEqual(row["provider"], "outlook")
        self.assertEqual(row["account_type"], "outlook")

    def test_auto_import_can_explicitly_join_pool(self):
        client = self.app.test_client()
        self._login(client)

        email_addr = f"auto_join_{uuid.uuid4().hex}@gmail.com"
        resp = client.post(
            "/api/accounts",
            json={
                "provider": "auto",
                "group_id": None,
                "duplicate_strategy": "skip",
                "add_to_pool": True,
                "account_string": f"{email_addr}----imap-pass",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))

        row = self._account_row(email_addr)
        self.assertIsNotNone(row)
        self.assertEqual(row["pool_status"], "available")
        self.assertEqual(row["provider"], "gmail")
        self.assertEqual(row["account_type"], "imap")


if __name__ == "__main__":
    unittest.main()
