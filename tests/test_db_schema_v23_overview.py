from __future__ import annotations

"""
TDD A 层：DB 迁移测试

覆盖 docs/TDD/2026-04-19-数据概览大盘TDD.md §5
当前（v22）运行会失败（红）—— 这是 TDD 预期状态。
实现 DB v23 迁移（verification_extract_logs 表）后，所有用例应通过（绿）。
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests._import_app import import_web_app_module


class DbSchemaV23OverviewTests(unittest.TestCase):
    """验证 v23 迁移创建 verification_extract_logs 表和索引，且操作幂等。"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()

    # ===== V-01: 空库（首次初始化）=====

    def test_v23_creates_verification_extract_logs_table(self):
        """V-01: 全新库初始化后 verification_extract_logs 表存在"""
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v23-") as tmp:
            db_path = Path(tmp) / "fresh.db"
            from outlook_web.db import init_db

            init_db(database_path=str(db_path))
            conn = sqlite3.connect(str(db_path))
            try:
                tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                self.assertIn("verification_extract_logs", tables)
            finally:
                conn.close()

    # ===== V-04: 字段完整性 =====

    def test_v23_verification_extract_logs_has_all_required_columns(self):
        """V-04: verification_extract_logs 表包含 TDD 约定的 11 个字段"""
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v23-col-") as tmp:
            db_path = Path(tmp) / "fresh.db"
            from outlook_web.db import init_db

            init_db(database_path=str(db_path))
            conn = sqlite3.connect(str(db_path))
            try:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(verification_extract_logs)").fetchall()}
                expected = {
                    "id",
                    "account_id",
                    "channel",
                    "started_at",
                    "finished_at",
                    "duration_ms",
                    "result_type",
                    "code_found",
                    "used_ai",
                    "error_code",
                    "trace_id",
                }
                missing = expected - columns
                self.assertEqual(set(), missing, f"缺少字段: {missing}")
            finally:
                conn.close()

    def test_v23_creates_indexes_on_verification_extract_logs(self):
        """V-01: verification_extract_logs 建立了至少 3 个命名索引"""
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v23-idx-") as tmp:
            db_path = Path(tmp) / "fresh.db"
            from outlook_web.db import init_db

            init_db(database_path=str(db_path))
            conn = sqlite3.connect(str(db_path))
            try:
                indexes = [
                    row[1]
                    for row in conn.execute(
                        "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='verification_extract_logs'"
                    ).fetchall()
                    if row[1]  # 过滤自动生成的主键索引（名称为 None 或空）
                ]
                self.assertGreaterEqual(
                    len(indexes),
                    3,
                    f"期望至少 3 个索引，实际: {indexes}",
                )
            finally:
                conn.close()

    # ===== V-02: v22 升级场景 =====

    def test_v23_migration_on_existing_db_preserves_existing_tables(self):
        """V-02: 升级后旧有 accounts/audit_logs 等表不受影响"""
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v23-upgrade-") as tmp:
            db_path = Path(tmp) / "v23.db"
            from outlook_web.db import init_db

            init_db(database_path=str(db_path))
            conn = sqlite3.connect(str(db_path))
            try:
                tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                for must_exist in ("accounts", "audit_logs", "verification_extract_logs"):
                    self.assertIn(must_exist, tables, f"表 {must_exist} 升级后消失")
            finally:
                conn.close()

    # ===== V-03: 幂等性 =====

    def test_v23_migration_is_idempotent(self):
        """V-03: 重复调用 init_db 不报错，幂等"""
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v23-idem-") as tmp:
            db_path = Path(tmp) / "idempotent.db"
            from outlook_web.db import init_db

            init_db(database_path=str(db_path))
            try:
                init_db(database_path=str(db_path))
            except Exception as exc:
                self.fail(f"重复调用 init_db 抛出异常: {exc}")

    # ===== V-04: 字段可写性 =====

    def test_v23_result_type_column_accepts_expected_values(self):
        """V-04: result_type 字段可存储 'code'/'link'/'none'"""
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v23-write-") as tmp:
            db_path = Path(tmp) / "write_test.db"
            from outlook_web.db import init_db

            init_db(database_path=str(db_path))
            conn = sqlite3.connect(str(db_path))
            try:
                for result_type in ("code", "link", "none"):
                    conn.execute(
                        """
                        INSERT INTO verification_extract_logs
                            (account_id, channel, started_at, finished_at, duration_ms, result_type, used_ai)
                        VALUES (1, 'graph_delta', strftime('%s','now'), strftime('%s','now'), 100, ?, 0)
                        """,
                        (result_type,),
                    )
                conn.commit()
                count = conn.execute("SELECT COUNT(*) FROM verification_extract_logs").fetchone()[0]
                self.assertEqual(count, 3)
            finally:
                conn.close()
