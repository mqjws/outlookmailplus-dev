"""
tests/test_pool_project_scoped.py
PR#27: 验证 project-scoped pool reuse 和 claim_token baseline 过滤。
"""

import unittest
from datetime import datetime, timezone


class TestBaselineTimestampFilter(unittest.TestCase):
    """验证 filter_messages 的 baseline_timestamp 参数。"""

    def _make_msg(self, timestamp: int, subject: str = "Test") -> dict:
        return {
            "id": f"msg_{timestamp}",
            "email_address": "test@example.com",
            "from_address": "sender@example.com",
            "subject": subject,
            "timestamp": timestamp,
            "created_at": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    def test_no_baseline_returns_all(self):
        from outlook_web.services.external_api import filter_messages

        msgs = [self._make_msg(1000), self._make_msg(2000), self._make_msg(3000)]
        result = filter_messages(msgs)
        self.assertEqual(len(result), 3)

    def test_baseline_filters_older_messages(self):
        from outlook_web.services.external_api import filter_messages

        msgs = [
            self._make_msg(1000),
            self._make_msg(2000),
            self._make_msg(3000),
        ]
        result = filter_messages(msgs, baseline_timestamp=2000)
        # 只保留 timestamp >= 2000 的
        self.assertEqual(len(result), 2)
        timestamps = sorted(m["timestamp"] for m in result)
        self.assertEqual(timestamps, [2000, 3000])

    def test_baseline_zero_does_not_filter(self):
        from outlook_web.services.external_api import filter_messages

        msgs = [self._make_msg(1000), self._make_msg(2000)]
        result = filter_messages(msgs, baseline_timestamp=0)
        self.assertEqual(len(result), 2)

    def test_baseline_filters_combined_with_from_contains(self):
        from outlook_web.services.external_api import filter_messages

        msgs = [
            {**self._make_msg(1000), "from_address": "a@example.com"},
            {**self._make_msg(2000), "from_address": "b@example.com"},
            {**self._make_msg(3000), "from_address": "a@example.com"},
        ]
        result = filter_messages(msgs, from_contains="a@", baseline_timestamp=1500)
        # from "a@" 且 timestamp >= 1500 → 只有 ts=3000
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["timestamp"], 3000)


class TestClaimedAtToTimestamp(unittest.TestCase):
    """验证 claimed_at_to_timestamp 工具函数。"""

    def test_valid_iso_string(self):
        from outlook_web.services.external_api import claimed_at_to_timestamp

        ts = claimed_at_to_timestamp("2026-04-01T12:00:00Z")
        self.assertIsNotNone(ts)
        self.assertIsInstance(ts, int)
        self.assertGreater(ts, 0)

    def test_empty_string_returns_none(self):
        from outlook_web.services.external_api import claimed_at_to_timestamp

        self.assertIsNone(claimed_at_to_timestamp(""))
        self.assertIsNone(claimed_at_to_timestamp(None))

    def test_invalid_string_returns_none(self):
        from outlook_web.services.external_api import claimed_at_to_timestamp

        self.assertIsNone(claimed_at_to_timestamp("not-a-date"))


class TestEmailDomainNormalization(unittest.TestCase):
    """验证 accounts 仓储层的 email_domain 归一化函数。"""

    def test_normalize_extracts_domain(self):
        from outlook_web.repositories.accounts import _normalize_account_email_domain

        self.assertEqual(_normalize_account_email_domain("user@Outlook.COM"), "outlook.com")
        self.assertEqual(_normalize_account_email_domain("user@gmail.com"), "gmail.com")
        self.assertEqual(
            _normalize_account_email_domain("user@corp.onmicrosoft.com"),
            "corp.onmicrosoft.com",
        )

    def test_normalize_no_at_sign(self):
        from outlook_web.repositories.accounts import _normalize_account_email_domain

        self.assertEqual(_normalize_account_email_domain("no-at-sign"), "")
        self.assertEqual(_normalize_account_email_domain(""), "")

    def test_normalize_whitespace(self):
        from outlook_web.repositories.accounts import _normalize_account_email_domain

        self.assertEqual(_normalize_account_email_domain("user@  EXAMPLE.COM  "), "example.com")


class TestPoolRepoClaimContext(unittest.TestCase):
    """验证 pool repo 中 get_claim_context 和 append_claim_read_context。"""

    @classmethod
    def setUpClass(cls):
        import os
        import tempfile

        from outlook_web.db import create_sqlite_connection, init_db

        cls.db_fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.close(cls.db_fd)
        init_db(cls.db_path)
        cls.db_path = cls.db_path

    @classmethod
    def tearDownClass(cls):
        import os

        try:
            os.unlink(cls.db_path)
        except Exception:
            pass

    def _conn(self):
        from outlook_web.db import create_sqlite_connection

        return create_sqlite_connection(self.db_path)

    def _insert_account(self, email: str, pool_status: str = "claimed", claim_token: str = "clm_test123") -> int:
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO accounts (
                    email, client_id, refresh_token, status,
                    account_type, provider, group_id, pool_status,
                    claim_token, claimed_by, claimed_at,
                    email_domain
                )
                VALUES (?, 'cid', 'rt', 'active', 'outlook', 'outlook', 1, ?, ?, 'bot:task1', '2026-04-01T12:00:00Z', ?)
                """,
                (email, pool_status, claim_token, email.rsplit("@", 1)[-1].lower()),
            )
            conn.commit()
            row = conn.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()
            return row["id"]
        finally:
            conn.close()

    def test_get_claim_context_returns_context(self):
        from outlook_web.repositories.pool import get_claim_context

        email = "ctx_test@outlook.com"
        token = "clm_ctx_001"
        account_id = self._insert_account(email, claim_token=token)
        conn = self._conn()
        try:
            ctx = get_claim_context(conn, token)
            self.assertIsNotNone(ctx)
            self.assertEqual(ctx["email"], email)
            self.assertEqual(ctx["claimed_at"], "2026-04-01T12:00:00Z")
            self.assertEqual(ctx["email_domain"], "outlook.com")
        finally:
            conn.close()

    def test_get_claim_context_unknown_token_returns_none(self):
        from outlook_web.repositories.pool import get_claim_context

        conn = self._conn()
        try:
            ctx = get_claim_context(conn, "clm_nonexistent_xyz")
            self.assertIsNone(ctx)
        finally:
            conn.close()

    def test_append_claim_read_context_inserts_log(self):
        from outlook_web.repositories.pool import append_claim_read_context

        email = "readlog_test@outlook.com"
        token = "clm_readlog_002"
        account_id = self._insert_account(email, claim_token=token)
        conn = self._conn()
        try:
            append_claim_read_context(conn, account_id, token, "bot", "task2", "test read")
            row = conn.execute(
                "SELECT * FROM account_claim_logs WHERE claim_token = ? AND action = 'read'",
                (token,),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["action"], "read")
            self.assertEqual(row["detail"], "test read")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
