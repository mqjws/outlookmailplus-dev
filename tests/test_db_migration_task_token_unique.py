from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests._import_app import import_web_app_module


class DbMigrationTaskTokenUniqueTests(unittest.TestCase):
    """覆盖 BUG-01：老库升级时 task_token 唯一约束补齐与重复检测。"""

    @classmethod
    def setUpClass(cls):
        # 复用统一的测试导入入口，确保必要环境变量（LOGIN_PASSWORD 等）已注入。
        cls.module = import_web_app_module()

    def _seed_legacy_db(self, db_path: Path, *, duplicate_token: bool) -> None:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('db_schema_version', '14')")

            # 旧库：temp_emails 有 task_token 列，但没有 UNIQUE 约束。
            conn.execute("""
                CREATE TABLE IF NOT EXISTS temp_emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'active',
                    task_token TEXT
                )
                """)
            conn.execute("DELETE FROM temp_emails")

            token_a = "tmptask_dup" if duplicate_token else "tmptask_unique_1"
            token_b = "tmptask_dup" if duplicate_token else "tmptask_unique_2"
            conn.execute(
                "INSERT INTO temp_emails (email, status, task_token) VALUES (?, 'active', ?)",
                ("a@temp.example", token_a),
            )
            conn.execute(
                "INSERT INTO temp_emails (email, status, task_token) VALUES (?, 'active', ?)",
                ("b@temp.example", token_b),
            )
            conn.commit()
        finally:
            conn.close()

    def test_init_db_aborts_when_duplicate_task_token_found(self):
        with tempfile.TemporaryDirectory(prefix="outlookEmail-migration-") as tmp:
            db_path = Path(tmp) / "legacy.db"
            self._seed_legacy_db(db_path, duplicate_token=True)

            from outlook_web.db import init_db

            with self.assertRaises(Exception) as ctx:
                init_db(database_path=str(db_path))

            message = str(ctx.exception)
            self.assertIn("temp_emails.task_token", message)
            self.assertIn("存在重复值", message)
            # 确保错误信息包含可执行 SQL 指引（便于线上排障）。
            self.assertIn("SELECT task_token, COUNT(*) AS c", message)
            self.assertIn("UPDATE temp_emails", message)

            conn = sqlite3.connect(str(db_path))
            try:
                # 失败时应记录到 schema_migrations，且不要创建唯一索引。
                row = conn.execute("SELECT status, error FROM schema_migrations ORDER BY id DESC LIMIT 1").fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], "failed")
                self.assertIn("task_token", str(row[1] or ""))

                idx_row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_temp_emails_task_token_unique'"
                ).fetchone()
                self.assertIsNone(idx_row)
            finally:
                conn.close()

    def test_init_db_creates_unique_index_when_no_duplicates(self):
        with tempfile.TemporaryDirectory(prefix="outlookEmail-migration-") as tmp:
            db_path = Path(tmp) / "legacy.db"
            self._seed_legacy_db(db_path, duplicate_token=False)

            from outlook_web.db import DB_SCHEMA_VERSION, init_db

            init_db(database_path=str(db_path))

            conn = sqlite3.connect(str(db_path))
            try:
                version_row = conn.execute("SELECT value FROM settings WHERE key = 'db_schema_version'").fetchone()
                self.assertIsNotNone(version_row)
                # init_db 会升级到当前最新 schema 版本（不应固定断言到历史版本）
                self.assertEqual(str(version_row[0]), str(DB_SCHEMA_VERSION))

                idx_row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_temp_emails_task_token_unique'"
                ).fetchone()
                self.assertIsNotNone(idx_row)

                # PRAGMA index_list 返回列：seq, name, unique, origin, partial
                idx_list = conn.execute("PRAGMA index_list('temp_emails')").fetchall()
                unique_flag = None
                for item in idx_list:
                    if item[1] == "idx_temp_emails_task_token_unique":
                        unique_flag = item[2]
                        break
                self.assertEqual(unique_flag, 1)

                # 验证唯一约束真实生效：插入重复 task_token 应触发 IntegrityError。
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO temp_emails (email, status, task_token) VALUES (?, 'active', ?)",
                        ("c@temp.example", "tmptask_unique_1"),
                    )
                    conn.commit()
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
