import json
import unittest
import uuid
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class RefreshSelectedIssue45Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
        self._cleanup_accounts()

    def tearDown(self):
        self._cleanup_accounts()

    def _cleanup_accounts(self):
        conn = self.module.create_sqlite_connection()
        try:
            conn.execute("DELETE FROM account_refresh_logs")
            conn.execute("DELETE FROM account_claim_logs")
            conn.execute("DELETE FROM account_project_usage")
            conn.execute("DELETE FROM accounts")
            conn.commit()
        finally:
            conn.close()

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json().get("success"), True)

    def _default_group_id(self) -> int:
        conn = self.module.create_sqlite_connection()
        try:
            row = conn.execute("SELECT id FROM groups WHERE name = '默认分组' LIMIT 1").fetchone()
            return int(row["id"]) if row else 1
        finally:
            conn.close()

    def _insert_outlook_account(self, *, unique: str) -> int:
        email_addr = f"selected_out_{unique}@outlook.com"
        conn = self.module.create_sqlite_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO accounts (
                    email, password, client_id, refresh_token,
                    account_type, provider, group_id, remark, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_addr,
                    "",
                    f"client_{unique}",
                    self.module.encrypt_data(f"rt_{unique}"),
                    "outlook",
                    "outlook",
                    self._default_group_id(),
                    "",
                    "active",
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def _insert_imap_account(self, *, unique: str) -> int:
        email_addr = f"selected_imap_{unique}@example.com"
        conn = self.module.create_sqlite_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO accounts (
                    email, password, client_id, refresh_token,
                    account_type, provider,
                    imap_host, imap_port, imap_password,
                    group_id, remark, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_addr,
                    "",
                    "",
                    self.module.encrypt_data(f"imap_rt_{unique}"),
                    "imap",
                    "qq",
                    "imap.qq.com",
                    993,
                    self.module.encrypt_data(f"imap_pw_{unique}"),
                    self._default_group_id(),
                    "",
                    "active",
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def _parse_sse_events(self, payload: str):
        events = []
        for line in payload.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
        return events

    def _get_account_refresh_token(self, account_id: int) -> str:
        conn = self.module.create_sqlite_connection()
        try:
            row = conn.execute("SELECT refresh_token FROM accounts WHERE id = ?", (account_id,)).fetchone()
            return self.module.decrypt_data(row["refresh_token"])
        finally:
            conn.close()

    def _count_refresh_logs(self, account_id: int, refresh_type: str) -> int:
        conn = self.module.create_sqlite_connection()
        try:
            row = conn.execute(
                """
                SELECT COUNT(1) AS cnt
                FROM account_refresh_logs
                WHERE account_id = ? AND refresh_type = ?
                """,
                (account_id, refresh_type),
            ).fetchone()
            return int(row["cnt"] if row else 0)
        finally:
            conn.close()

    def test_selected_refresh_mixed_accounts_streams_outlook_only_and_skips_imap(self):
        client = self.app.test_client()
        self._login(client)

        unique = uuid.uuid4().hex
        outlook_id = self._insert_outlook_account(unique=unique)
        imap_id = self._insert_imap_account(unique=unique)
        refresh_calls = []

        def fake_refresh(client_id, refresh_token, proxy_url):
            refresh_calls.append((client_id, refresh_token, proxy_url))
            return True, None, f"rt_new_{unique}"

        with (
            patch(
                "outlook_web.services.graph.test_refresh_token_with_rotation",
                side_effect=fake_refresh,
            ),
            patch(
                "outlook_web.services.refresh.acquire_distributed_lock",
                return_value=(True, {}),
            ),
            patch("outlook_web.services.refresh.release_distributed_lock"),
            patch("outlook_web.services.refresh.time.sleep"),
        ):
            resp = client.post(
                "/api/accounts/refresh/selected",
                json={"account_ids": [outlook_id, imap_id]},
            )

        self.assertEqual(resp.status_code, 200)
        events = self._parse_sse_events(resp.get_data(as_text=True))
        self.assertGreaterEqual(len(events), 3)

        start_event = events[0]
        self.assertEqual(start_event.get("type"), "start")
        self.assertEqual(start_event.get("total"), 1)
        self.assertEqual(start_event.get("skipped_count"), 1)

        complete_event = events[-1]
        self.assertEqual(complete_event.get("type"), "complete")
        self.assertEqual(complete_event.get("total"), 1)
        self.assertEqual(complete_event.get("success_count"), 1)
        self.assertEqual(complete_event.get("failed_count"), 0)

        self.assertEqual(len(refresh_calls), 1)
        self.assertEqual(refresh_calls[0][0], f"client_{unique}")
        self.assertEqual(refresh_calls[0][1], f"rt_{unique}")

        self.assertEqual(self._get_account_refresh_token(outlook_id), f"rt_new_{unique}")
        self.assertEqual(self._get_account_refresh_token(imap_id), f"imap_rt_{unique}")

        self.assertEqual(
            self._count_refresh_logs(account_id=outlook_id, refresh_type="manual_selected"),
            1,
        )
        self.assertEqual(
            self._count_refresh_logs(account_id=imap_id, refresh_type="manual_selected"),
            0,
        )
