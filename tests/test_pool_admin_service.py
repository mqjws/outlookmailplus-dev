from __future__ import annotations

"""
TDD B 层：号池管理 Service 测试

覆盖 docs/TDD/2026-05-18-Issue60-号池管理UI与状态维护TDD.md §6
当前运行会失败（红）—— pool_admin service 模块尚未创建。
实现 outlook_web/services/pool_admin.py 后，所有用例应通过（绿）。

测试目标：
1. [MVP] NULL -> available 动作（移入号池）
2. [MVP] available -> NULL 动作（移出号池）
3. [MVP] claimed 通用动作拒绝（显式保护）
4. [增强] force_release 仅对 claimed 有效
5. [增强] force_release 是独立动作，不是通用更新分支的特例放行
"""

import secrets
import unittest

from tests._import_app import import_web_app_module


class PoolAdminServiceBase(unittest.TestCase):
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
        status="active",
    ):
        email = f"svc_admin_{secrets.token_hex(4)}{email_suffix}@example.com"
        conn.execute(
            """
            INSERT INTO accounts (email, client_id, refresh_token, status, pool_status, provider)
            VALUES (?, 'test_client', 'test_token', ?, ?, ?)
            """,
            (email, status, pool_status, provider),
        )
        conn.commit()
        row = conn.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()
        return row["id"]

    def _make_claimed_account(self, conn, *, caller_id="bot1", task_id="task1"):
        from datetime import datetime, timedelta, timezone

        account_id = self._make_account(conn, pool_status="available")
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


# ===== MVP: §6.1 通用动作规则 =====


class PoolAdminServiceActionTests(PoolAdminServiceBase):
    """Service 层动作规则测试"""

    def setUp(self):
        self.conn = self.create_conn()
        self.conn.execute("DELETE FROM account_claim_logs")
        self.conn.execute("DELETE FROM accounts")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_apply_action_allows_move_into_pool_from_null(self):
        """A-01: NULL -> available (move_into_pool)"""
        from outlook_web.services import pool_admin as svc

        account_id = self._make_account(self.conn, pool_status=None)

        result = svc.apply_action(account_id=account_id, action="move_into_pool")

        self.assertTrue(result.get("success"), f"move_into_pool 应成功: {result}")
        row = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertEqual(row["pool_status"], "available")

    def test_apply_action_allows_move_out_of_pool_from_available(self):
        """A-02: available -> NULL (move_out_of_pool)"""
        from outlook_web.services import pool_admin as svc

        account_id = self._make_account(self.conn, pool_status="available")

        result = svc.apply_action(account_id=account_id, action="move_out_of_pool")

        self.assertTrue(result.get("success"), f"move_out_of_pool 应成功: {result}")
        row = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertIsNone(row["pool_status"])

    def test_apply_action_allows_restore_available_from_used(self):
        """A-03: used -> available (restore_available)"""
        from outlook_web.services import pool_admin as svc

        account_id = self._make_account(self.conn, pool_status="used")

        result = svc.apply_action(account_id=account_id, action="restore_available")

        self.assertTrue(result.get("success"), f"restore_available 应成功: {result}")
        row = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertEqual(row["pool_status"], "available")

    def test_apply_action_allows_freeze_from_available(self):
        """A-06: available -> frozen (freeze)"""
        from outlook_web.services import pool_admin as svc

        account_id = self._make_account(self.conn, pool_status="available")

        result = svc.apply_action(account_id=account_id, action="freeze")

        self.assertTrue(result.get("success"), f"freeze 应成功: {result}")
        row = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertEqual(row["pool_status"], "frozen")


# ===== MVP: §6.3 claimed 保护 =====


class PoolAdminServiceClaimedProtectionTests(PoolAdminServiceBase):
    """Service 层 claimed 保护测试 — 显式独立覆盖"""

    def setUp(self):
        self.conn = self.create_conn()
        self.conn.execute("DELETE FROM account_claim_logs")
        self.conn.execute("DELETE FROM accounts")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_apply_action_rejects_move_out_of_pool_on_claimed(self):
        """C-01: claimed 状态拒绝 move_out_of_pool"""
        from outlook_web.services import pool_admin as svc

        account_id, _ = self._make_claimed_account(self.conn)

        result = svc.apply_action(account_id=account_id, action="move_out_of_pool")

        self.assertFalse(result.get("success"), "claimed 账号应拒绝 move_out_of_pool")
        # 确认状态未被改变
        row = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertEqual(row["pool_status"], "claimed")

    def test_apply_action_rejects_restore_available_on_claimed(self):
        """C-02: claimed 状态拒绝 restore_available"""
        from outlook_web.services import pool_admin as svc

        account_id, _ = self._make_claimed_account(self.conn)

        result = svc.apply_action(account_id=account_id, action="restore_available")

        self.assertFalse(result.get("success"), "claimed 账号应拒绝 restore_available")
        row = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertEqual(row["pool_status"], "claimed")

    def test_apply_action_rejects_freeze_on_claimed(self):
        """C-03: claimed 状态拒绝 freeze"""
        from outlook_web.services import pool_admin as svc

        account_id, _ = self._make_claimed_account(self.conn)

        result = svc.apply_action(account_id=account_id, action="freeze")

        self.assertFalse(result.get("success"), "claimed 账号应拒绝 freeze")
        row = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertEqual(row["pool_status"], "claimed")

    def test_apply_action_rejects_retire_on_claimed(self):
        """C-04: claimed 状态拒绝 retire"""
        from outlook_web.services import pool_admin as svc

        account_id, _ = self._make_claimed_account(self.conn)

        result = svc.apply_action(account_id=account_id, action="retire")

        self.assertFalse(result.get("success"), "claimed 账号应拒绝 retire")
        row = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertEqual(row["pool_status"], "claimed")

    def test_apply_action_returns_stable_error_for_claimed_protection(self):
        """所有 claimed 拒绝应返回稳定错误码/信息"""
        from outlook_web.services import pool_admin as svc

        account_id, _ = self._make_claimed_account(self.conn)

        for action in ["move_out_of_pool", "restore_available", "freeze", "retire"]:
            result = svc.apply_action(account_id=account_id, action=action)
            self.assertFalse(result.get("success"))
            # 应包含明确的错误信息或错误码
            self.assertTrue(
                result.get("error") or result.get("message") or result.get("error_code"),
                f"claimed 拒绝时应有明确错误信息 (action={action})",
            )


# ===== MVP: §6.2 非法动作拦截 =====


class PoolAdminServiceInvalidActionTests(PoolAdminServiceBase):
    """Service 层非法动作拦截测试"""

    def setUp(self):
        self.conn = self.create_conn()
        self.conn.execute("DELETE FROM account_claim_logs")
        self.conn.execute("DELETE FROM accounts")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_apply_action_rejects_move_into_pool_when_already_in_pool(self):
        """已在池内的账号不能再次移入"""
        from outlook_web.services import pool_admin as svc

        account_id = self._make_account(self.conn, pool_status="available")

        result = svc.apply_action(account_id=account_id, action="move_into_pool")

        self.assertFalse(result.get("success"), "已在池内应拒绝 move_into_pool")

    def test_apply_action_rejects_move_out_of_pool_when_null(self):
        """池外账号不能再移出"""
        from outlook_web.services import pool_admin as svc

        account_id = self._make_account(self.conn, pool_status=None)

        result = svc.apply_action(account_id=account_id, action="move_out_of_pool")

        self.assertFalse(result.get("success"), "池外账号应拒绝 move_out_of_pool")

    def test_apply_action_rejects_invalid_action_name(self):
        """无效动作名称应被拒绝"""
        from outlook_web.services import pool_admin as svc

        account_id = self._make_account(self.conn, pool_status="available")

        result = svc.apply_action(account_id=account_id, action="hack_the_planet")

        self.assertFalse(result.get("success"), "无效动作应被拒绝")


# ===== 增强项: §6.4 强制释放 =====


class PoolAdminServiceForceReleaseTests(PoolAdminServiceBase):
    """Service 层强制释放测试（增强项）"""

    def setUp(self):
        self.conn = self.create_conn()
        self.conn.execute("DELETE FROM account_claim_logs")
        self.conn.execute("DELETE FROM accounts")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_force_release_only_allows_claimed_account(self):
        """F-02: 非 claimed 账号不能执行 force_release"""
        from outlook_web.services import pool_admin as svc

        account_id = self._make_account(self.conn, pool_status="available")

        result = svc.apply_action(account_id=account_id, action="force_release")

        self.assertFalse(result.get("success"), "非 claimed 账号应拒绝 force_release")

    def test_force_release_success_for_claimed(self):
        """F-01: claimed 账号可强制释放"""
        from outlook_web.services import pool_admin as svc

        account_id, _ = self._make_claimed_account(self.conn)

        result = svc.apply_action(account_id=account_id, action="force_release")

        self.assertTrue(result.get("success"), "claimed 账号应允许 force_release")
        row = self.conn.execute("SELECT pool_status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertEqual(row["pool_status"], "available")

    def test_force_release_is_not_generic_update_bypass(self):
        """force_release 是独立动作，不能绕过通用 claimed 保护"""
        from outlook_web.services import pool_admin as svc

        account_id, _ = self._make_claimed_account(self.conn)

        # 通用动作仍被拒绝
        for action in ["move_out_of_pool", "freeze", "retire"]:
            result = svc.apply_action(account_id=account_id, action=action)
            self.assertFalse(result.get("success"), f"通用动作 {action} 应仍被拒绝")

        # 只有 force_release 能通过
        result = svc.apply_action(account_id=account_id, action="force_release")
        self.assertTrue(result.get("success"), "force_release 应成功")


if __name__ == "__main__":
    unittest.main()
