import unittest
import uuid

from tests._import_app import clear_login_attempts, import_web_app_module


class AccountRemarkOnlyUpdateTests(unittest.TestCase):
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
        data = resp.get_json()
        self.assertEqual(data.get("success"), True)

    def _default_group_id(self) -> int:
        conn = self.module.create_sqlite_connection()
        try:
            row = conn.execute("SELECT id FROM groups WHERE name = '默认分组' LIMIT 1").fetchone()
            return int(row["id"]) if row else 1
        finally:
            conn.close()

    def _insert_outlook_account(self, *, remark: str):
        unique = uuid.uuid4().hex
        email_addr = f"remark_edit_{unique}@outlook.com"
        password = f"pw_{unique}"
        client_id = f"cid_{unique}"
        refresh_token = f"rt_{unique}----tail"
        group_id = self._default_group_id()

        conn = self.module.create_sqlite_connection()
        try:
            cur = conn.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, account_type, provider, group_id, remark, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_addr,
                    self.module.encrypt_data(password),
                    client_id,
                    self.module.encrypt_data(refresh_token),
                    "outlook",
                    "outlook",
                    group_id,
                    remark,
                    "active",
                ),
            )
            conn.commit()
            account_id = int(cur.lastrowid)
        finally:
            conn.close()

        return {
            "id": account_id,
            "email": email_addr,
            "password": password,
            "client_id": client_id,
            "refresh_token": refresh_token,
            "group_id": group_id,
            "remark": remark,
        }

    def _insert_imap_account(self, *, remark: str):
        unique = uuid.uuid4().hex
        email_addr = f"remark_edit_{unique}@gmail.com"
        imap_password = f"imap_pw_{unique}"
        group_id = self._default_group_id()

        conn = self.module.create_sqlite_connection()
        try:
            cur = conn.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, account_type, provider, imap_host, imap_port, imap_password, group_id, remark, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_addr,
                    "",
                    "",
                    "",
                    "imap",
                    "gmail",
                    "imap.gmail.com",
                    993,
                    self.module.encrypt_data(imap_password),
                    group_id,
                    remark,
                    "active",
                ),
            )
            conn.commit()
            account_id = int(cur.lastrowid)
        finally:
            conn.close()

        return {
            "id": account_id,
            "email": email_addr,
            "imap_password": imap_password,
            "group_id": group_id,
            "remark": remark,
        }

    def _get_account_row(self, account_id: int):
        conn = self.module.create_sqlite_connection()
        try:
            return conn.execute("SELECT * FROM accounts WHERE id = ? LIMIT 1", (account_id,)).fetchone()
        finally:
            conn.close()

    def _decrypt_if_needed(self, value: str) -> str:
        if not value:
            return value
        try:
            return self.module.decrypt_data(value)
        except Exception:
            return value

    def test_outlook_account_remark_only_update_succeeds_and_preserves_other_fields(self):
        client = self.app.test_client()
        self._login(client)
        account = self._insert_outlook_account(remark="old_remark")

        resp = client.put(
            f"/api/accounts/{account['id']}",
            json={
                "email": account["email"],
                "group_id": account["group_id"],
                "remark": "new_remark",
                "status": "active",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json().get("success"), True)

        row = self._get_account_row(account["id"])
        self.assertIsNotNone(row)
        self.assertEqual(row["email"], account["email"])
        self.assertEqual(row["client_id"], account["client_id"])
        self.assertEqual(self._decrypt_if_needed(row["password"]), account["password"])
        self.assertEqual(self._decrypt_if_needed(row["refresh_token"]), account["refresh_token"])
        self.assertEqual(int(row["group_id"]), account["group_id"])
        self.assertEqual((row["remark"] or ""), "new_remark")
        self.assertEqual(row["status"], "active")

    def test_outlook_account_remark_can_be_cleared_without_reentering_credentials(self):
        client = self.app.test_client()
        self._login(client)
        account = self._insert_outlook_account(remark="to_be_cleared")

        resp = client.put(
            f"/api/accounts/{account['id']}",
            json={
                "email": account["email"],
                "group_id": account["group_id"],
                "remark": "",
                "status": "active",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json().get("success"), True)

        row = self._get_account_row(account["id"])
        self.assertIsNotNone(row)
        self.assertEqual((row["remark"] or ""), "")
        self.assertEqual(row["client_id"], account["client_id"])
        self.assertEqual(self._decrypt_if_needed(row["refresh_token"]), account["refresh_token"])

    def test_outlook_account_refresh_token_update_succeeds_when_client_id_is_present(self):
        client = self.app.test_client()
        self._login(client)
        account = self._insert_outlook_account(remark="keep")
        new_refresh_token = f"rt_new_{uuid.uuid4().hex}----tail"

        resp = client.put(
            f"/api/accounts/{account['id']}",
            json={
                "email": account["email"],
                "client_id": account["client_id"],
                "refresh_token": new_refresh_token,
                "group_id": account["group_id"],
                "remark": account["remark"],
                "status": "active",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json().get("success"), True)

        row = self._get_account_row(account["id"])
        self.assertIsNotNone(row)
        self.assertEqual(row["client_id"], account["client_id"])
        self.assertEqual(self._decrypt_if_needed(row["refresh_token"]), new_refresh_token)
        self.assertEqual(self._decrypt_if_needed(row["password"]), account["password"])

    def test_outlook_account_client_id_change_requires_refresh_token(self):
        client = self.app.test_client()
        self._login(client)
        account = self._insert_outlook_account(remark="keep")
        original_row = self._get_account_row(account["id"])
        self.assertIsNotNone(original_row)

        resp = client.put(
            f"/api/accounts/{account['id']}",
            json={
                "email": account["email"],
                "client_id": f"{account['client_id']}_updated",
                "group_id": account["group_id"],
                "remark": account["remark"],
                "status": "active",
            },
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "OUTLOOK_REFRESH_TOKEN_REQUIRED")

        row = self._get_account_row(account["id"])
        self.assertIsNotNone(row)
        self.assertEqual(row["client_id"], original_row["client_id"])
        self.assertEqual(row["refresh_token"], original_row["refresh_token"])
        self.assertEqual((row["remark"] or ""), account["remark"])

    def test_imap_account_remark_only_update_still_preserves_imap_password(self):
        client = self.app.test_client()
        self._login(client)
        account = self._insert_imap_account(remark="imap_old")

        resp = client.put(
            f"/api/accounts/{account['id']}",
            json={
                "email": account["email"],
                "group_id": account["group_id"],
                "remark": "imap_new",
                "status": "active",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json().get("success"), True)

        row = self._get_account_row(account["id"])
        self.assertIsNotNone(row)
        self.assertEqual(row["account_type"], "imap")
        self.assertEqual((row["remark"] or ""), "imap_new")
        self.assertEqual(self._decrypt_if_needed(row["imap_password"]), account["imap_password"])
        self.assertEqual(row["client_id"], "")
        self.assertEqual(row["refresh_token"], "")
