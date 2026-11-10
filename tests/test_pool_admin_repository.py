from __future__ import annotations

"""
TDD A 层：号池管理 Repository 测试

覆盖 docs/TDD/2026-05-18-Issue60-号池管理UI与状态维护TDD.md §5
当前运行会失败（红）—— pool_admin repository 模块尚未创建。
实现 outlook_web/repositories/pool_admin.py 后，所有用例应通过（绿）。

测试目标：
1. [MVP] 池内筛选 (in_pool=true)
2. [MVP] 池外筛选 (in_pool=false)
3. [MVP] claimed 字段返回
4. [MVP] NULL -> available 状态更新
5. [MVP] available -> NULL 状态更新
6. [增强] force_release 清理 claim 上下文
"""

import secrets
import unittest

from tests._import_app import import_web_app_module


class PoolAdminRepositoryBase(unittest.TestCase):
    """公共 setUp：创建测试连接 + 辅助方法"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        from outlook_web.db import create_sqlite_connection

        cls.create_conn = staticmethod(lambda: create_sqlite_connection())

    def _make_account(
        self,
        conn,
        *,
        email_suffix="",
        pool_status=None,
        provider="outlook",
        account_type="outlook",
        group_id=None,
        status="active",
    ):
        """插入一条测试账号并返回其 id。pool_status=None 表示池外。"""
        email = f"pool_admin_{secrets.token_hex(4)}{email_suffix}@example.com"
        conn.execute(
            """
            INSERT INTO accounts (email, client_id, refresh_token, status, pool_status, provider, account_type, group_id)
            VALUES (?, 'test_client', 'test_token', ?, ?, ?, ?, ?)
            """,
            (email, status, pool_status, provider, account_type, group_id),
        )
        conn.commit()
        row = conn.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()
        return row["id"]

    def _make_claimed_account(self, conn, *, caller_id="bot1", task_id="task1"):
        """创建一个 claimed 状态账号，返回 (id, claim_token)。"""
        account_id = self._make_account(conn, pool_status="available")
        from datetime import datetime, timedelta, timezone

        now_str = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        expires_str = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=600)).isoformat() + "Z"
        token = "clm_" + secrets.token_urlsafe(9)
        conn.execute(
            """
            UPDATE accounts SET
                pool_status = 'claimed',
                claimed_by = ?,
                claimed_at = ?,
                lease_expires_at = ?,
                claim_token = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (f"{caller_id}:{task_id}", now_str, expires_str, token, now_str, account_id),
        )
        conn.commit()
        return account_id, token


# ===== MVP: Q-01 / Q-02 池内 / 池外筛选 =====


class PoolAdminListQueryTests(PoolAdminRepositoryBase):
    """Repository 层池内/池外查询测试"""

    def setUp(self):
        self.conn = self.create_conn()
        # 清理测试数据
        self.conn.execute("DELETE FROM account_claim_logs")
        self.conn.execute("DELETE FROM accounts")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    # --- Q-01: in_pool=true 仅返回 pool_status IS NOT NULL ---
    def test_list_accounts_returns_only_in_pool_accounts_when_in_pool_true(self):
        """Q-01: in_pool=true 仅返回 pool_status IS NOT NULL 的账号"""
        from outlook_web.repositories import pool_admin as repo

        id_in = self._make_account(self.conn, pool_status="available")
        id_in2 = self._make_account(self.conn, pool_status="cooldown")
        id_out = self._make_account(self.conn, pool_status=None)

        result = repo.list_accounts(self.conn, in_pool="true")
        returned_ids = [row["id"] for row in result.get("items", [])]
        self.assertIn(id_in, returned_ids, "available 账号应出现在池内结果")
        self.assertIn(id_in2, returned_ids, "cooldown 账号应出现在池内结果")
        self.assertNotIn(id_out, returned_ids, "pool_status=NULL 的账号不应出现在池内结果")

    # --- Q-02: in_pool=false 仅返回 pool_status IS NULL ---
    def test_list_accounts_returns_only_out_of_pool_accounts_when_in_pool_false(self):
        """Q-02: in_pool=false 仅返回 pool_status IS NULL 的账号"""
        from outlook_web.repositories import pool_admin as repo

        id_in = self._make_account(self.conn, pool_status="available")
        id_out = self._make_account(self.conn, pool_status=None)
        id_out2 = self._make_account(self.conn, pool_status=None)

        result = repo.list_accounts(self.conn, in_pool="false")
        returned_ids = [row["id"] for row in result.get("items", [])]
        self.assertIn(id_out, returned_ids, "pool_status=NULL 的账号应出现在池外结果")
        self.assertIn(id_out2, returned_ids)
        self.assertNotIn(id_in, returned_ids, "available 账号不应出现在池外结果")

    # --- Q-06: 空结果合法 ---
    def test_list_accounts_empty_result_is_legal(self):
        """Q-06: 空数据时返回合法结构"""
        from outlook_web.repositories import pool_admin as repo

        result = repo.list_accounts(self.conn, in_pool="true")
        self.assertIn("items", result)
        self.assertIsInstance(result["items"], list)
        self.assertEqual(len(result["items"]), 0)


# ===== MVP: Q-04 claimed 字段返回 =====


class PoolAdminClaimedFieldsTests(PoolAdminRepositoryBase):
    """Repository 层 claimed 相关字段返回测试"""

    def setUp(self):
        self.conn = self.create_conn()
        self.conn.execute("DELETE FROM account_claim_logs")
        self.conn.execute("DELETE FROM accounts")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_list_accounts_returns_claim_fields_for_claimed_rows(self):
        """Q-04: claimed 行应返回 claimed_by / claimed_at / lease_expires_at"""
        from outlook_web.repositories import pool_admin as repo

        account_id, _ = self._make_claimed_account(self.conn)

        result = repo.list_accounts(self.conn, in_pool="true", pool_status="claimed")
        items = result.get("items", [])
        self.assertTrue(len(items) > 0, "至少应返回一条 claimed 记录")

        claimed_item = None
        for item in items:
            if item["id"] == account_id:
                claimed_item = item
                break

        self.assertIsNotNone(claimed_item, "应找到指定的 claimed 账号")
        self.assertEqual(claimed_item["pool_status"], "claimed")
        self.assertIsNotNone(claimed_item.get("claimed_by"), "claimed_by 不应为 None")
        self.assertIsNotNone(claimed_item.get("claimed_at"), "claimed_at 不应为 None")
        self.assertIsNotNone(claimed_item.get("lease_expires_at"), "lease_expires_at 不应为 None")


# ===== MVP: A-01 / A-02 状态更新 =====


class PoolAdminStatusUpdateTests(PoolAdminRepositoryBase):
    """Repository 层状态更新测试"""

    def setUp(self):
        self.conn = self.create_conn()
        self.conn.execute("DELETE FROM account_claim_logs")
        self.conn.execute("DELETE FROM accounts")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_update_pool_status_moves_null_to_available(self):
        """A-01: NULL -> available（移入号池）"""
        from outlook_web.repositories import pool_admin as repo

        account_id = self._make_account(self.conn, pool_status=None)

        repo.update_pool_status(self.conn, account_id=account_id, new_pool_status="available")

        row = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertEqual(row["pool_status"], "available")

    def test_update_pool_status_moves_available_to_null(self):
        """A-02: available -> NULL（移出号池）"""
        from outlook_web.repositories import pool_admin as repo

        account_id = self._make_account(self.conn, pool_status="available")

        repo.update_pool_status(self.conn, account_id=account_id, new_pool_status=None)

        row = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertIsNone(row["pool_status"])

    def test_update_pool_status_does_not_affect_other_accounts(self):
        """状态更新不应影响其他账号"""
        from outlook_web.repositories import pool_admin as repo

        account_id_1 = self._make_account(self.conn, pool_status=None)
        account_id_2 = self._make_account(self.conn, pool_status="available")

        repo.update_pool_status(self.conn, account_id=account_id_1, new_pool_status="available")

        row2 = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id_2,)).fetchone()
        self.assertEqual(row2["pool_status"], "available", "其他账号状态不应被改变")


# ===== 增强项: F-01 / F-03 强制释放 =====


class PoolAdminForceReleaseTests(PoolAdminRepositoryBase):
    """Repository 层强制释放测试（增强项）"""

    def setUp(self):
        self.conn = self.create_conn()
        self.conn.execute("DELETE FROM account_claim_logs")
        self.conn.execute("DELETE FROM accounts")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_force_release_clears_claim_context_and_sets_available(self):
        """F-01 + F-03: 强制释放将 claimed -> available，清理 claim 上下文"""
        from outlook_web.repositories import pool_admin as repo

        account_id, _ = self._make_claimed_account(self.conn)

        repo.force_release(self.conn, account_id=account_id)

        row = self.conn.execute(
            "SELECT pool_status, claimed_by, claimed_at, lease_expires_at, claim_token FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        self.assertEqual(row["pool_status"], "available")
        self.assertIsNone(row["claimed_by"])
        self.assertIsNone(row["claimed_at"])
        self.assertIsNone(row["lease_expires_at"])
        self.assertIsNone(row["claim_token"])

    def test_force_release_keeps_account_in_pool(self):
        """F-01 补充: 强制释放后账号仍在池内（pool_status != NULL）"""
        from outlook_web.repositories import pool_admin as repo

        account_id, _ = self._make_claimed_account(self.conn)

        repo.force_release(self.conn, account_id=account_id)

        row = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertIsNotNone(row["pool_status"], "强制释放后账号应仍在池内")
        self.assertEqual(row["pool_status"], "available")


if __name__ == "__main__":
    unittest.main()
