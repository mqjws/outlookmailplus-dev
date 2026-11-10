from __future__ import annotations

import unittest

from tests._import_app import import_web_app_module


class PoolRepositoryProjectReuseTests(unittest.TestCase):
    """覆盖 docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md 中的 Repository 级核心用例。"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            account_columns = [row[1] for row in db.execute("PRAGMA table_info(accounts)").fetchall()]
            if "claimed_project_key" not in account_columns:
                db.execute("ALTER TABLE accounts ADD COLUMN claimed_project_key TEXT DEFAULT NULL")
            usage_columns = [row[1] for row in db.execute("PRAGMA table_info(account_project_usage)").fetchall()]
            if "first_success_at" not in usage_columns:
                db.execute("ALTER TABLE account_project_usage ADD COLUMN first_success_at TEXT DEFAULT NULL")
            if "last_success_at" not in usage_columns:
                db.execute("ALTER TABLE account_project_usage ADD COLUMN last_success_at TEXT DEFAULT NULL")
            if "success_count" not in usage_columns:
                db.execute("ALTER TABLE account_project_usage ADD COLUMN success_count INTEGER NOT NULL DEFAULT 0")
            db.execute("DELETE FROM account_claim_logs")
            db.execute("DELETE FROM account_project_usage")
            db.execute("DELETE FROM accounts")
            db.commit()

    def _insert_available_account(
        self,
        *,
        email: str,
        provider: str = "outlook",
        account_type: str = "outlook",
        pool_status: str = "available",
        claimed_project_key: str | None = None,
        claim_token: str | None = None,
        claimed_by: str | None = None,
        claimed_at: str = "2026-04-16T10:00:00Z",
        lease_expires_at: str = "2026-04-16T10:10:00Z",
    ) -> int:
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (
                    email, client_id, refresh_token, status,
                    account_type, provider, group_id, pool_status,
                    claim_token, claimed_by, claimed_at, lease_expires_at,
                    claimed_project_key, email_domain
                )
                VALUES (?, 'cid', 'rt', 'active',
                        ?, ?, 1, ?,
                        ?, ?, ?, ?,
                        ?, ?)
                """,
                (
                    email,
                    account_type,
                    provider,
                    pool_status,
                    claim_token,
                    claimed_by,
                    claimed_at,
                    lease_expires_at,
                    claimed_project_key,
                    email.rsplit("@", 1)[-1].lower(),
                ),
            )
            db.commit()
            row = db.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()
            return int(row["id"])

    def _insert_usage_row(
        self,
        *,
        account_id: int,
        consumer_key: str,
        project_key: str,
        success_count: int = 0,
    ) -> None:
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            first_success_at = "2026-04-16T10:20:00Z" if success_count > 0 else None
            last_success_at = "2026-04-16T10:20:00Z" if success_count > 0 else None
            db.execute(
                """
                INSERT INTO account_project_usage (
                    account_id, consumer_key, project_key,
                    first_claimed_at, last_claimed_at,
                    first_success_at, last_success_at, success_count
                )
                VALUES (?, ?, ?, '2026-04-16T10:00:00Z', '2026-04-16T10:05:00Z', ?, ?, ?)
                """,
                (account_id, consumer_key, project_key, first_success_at, last_success_at, success_count),
            )
            db.commit()

    def test_claim_atomic_sets_claimed_project_key_when_project_reuse_enabled(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import pool as pool_repo

            account_id = self._insert_available_account(email="repo-claim@example.com")
            db = get_db()
            account = pool_repo.claim_atomic(
                db,
                caller_id="repo_bot",
                task_id="repo_task_1",
                lease_seconds=600,
                project_key="project_alpha",
                email_domain="example.com",
            )
            self.assertIsNotNone(account)
            row = db.execute("SELECT claimed_project_key FROM accounts WHERE id = ?", (account_id,)).fetchone()
            self.assertEqual(row["claimed_project_key"], "project_alpha")

    def test_claim_atomic_same_project_only_claim_trace_does_not_block(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import pool as pool_repo

            account_id = self._insert_available_account(email="repo-claim-trace@example.com")
            self._insert_usage_row(account_id=account_id, consumer_key="repo_bot", project_key="project_alpha")

            db = get_db()
            account = pool_repo.claim_atomic(
                db,
                caller_id="repo_bot",
                task_id="repo_task_2",
                lease_seconds=600,
                project_key="project_alpha",
                email_domain="example.com",
            )
            self.assertIsNotNone(account)
            self.assertEqual(account["id"], account_id)

    def test_claim_atomic_same_project_success_record_blocks(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import pool as pool_repo

            account_id = self._insert_available_account(email="repo-success-block@example.com")
            self._insert_usage_row(
                account_id=account_id,
                consumer_key="repo_bot",
                project_key="project_alpha",
                success_count=1,
            )

            db = get_db()
            account = pool_repo.claim_atomic(
                db,
                caller_id="repo_bot",
                task_id="repo_task_3",
                lease_seconds=600,
                project_key="project_alpha",
                email_domain="example.com",
            )
            self.assertIsNone(account)

    def test_claim_atomic_leaves_claimed_project_key_empty_without_project_key(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import pool as pool_repo

            account_id = self._insert_available_account(email="repo-no-project@example.com")
            db = get_db()
            account = pool_repo.claim_atomic(
                db,
                caller_id="repo_bot",
                task_id="repo_task_np",
                lease_seconds=600,
                email_domain="example.com",
            )
            self.assertIsNotNone(account)
            row = db.execute("SELECT claimed_project_key FROM accounts WHERE id = ?", (account_id,)).fetchone()
            self.assertIsNone(row["claimed_project_key"])

    def test_claim_atomic_different_project_success_record_still_allows_claim(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import pool as pool_repo

            account_id = self._insert_available_account(email="repo-diff-project@example.com")
            self._insert_usage_row(
                account_id=account_id,
                consumer_key="repo_bot",
                project_key="project_alpha",
                success_count=1,
            )

            db = get_db()
            account = pool_repo.claim_atomic(
                db,
                caller_id="repo_bot",
                task_id="repo_task_dp",
                lease_seconds=600,
                project_key="project_beta",
                email_domain="example.com",
            )
            self.assertIsNotNone(account)
            self.assertEqual(account["id"], account_id)

    def test_complete_reuse_path_success_returns_available_and_updates_success_record(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import pool as pool_repo

            account_id = self._insert_available_account(
                email="repo-complete@example.com",
                pool_status="claimed",
                claim_token="clm_repo_complete",
                claimed_by="repo_bot:repo_task_4",
                claimed_project_key="project_alpha",
            )

            db = get_db()
            new_status = pool_repo.complete(
                db,
                account_id=account_id,
                claim_token="clm_repo_complete",
                caller_id="repo_bot",
                task_id="repo_task_4",
                result="success",
                detail="repo success",
            )
            self.assertEqual(new_status, "available")

            account_row = db.execute(
                "SELECT pool_status, claimed_project_key, success_count FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            self.assertEqual(account_row["pool_status"], "available")
            self.assertIsNone(account_row["claimed_project_key"])
            self.assertGreaterEqual(account_row["success_count"], 1)

            usage_row = db.execute(
                """
                SELECT success_count
                FROM account_project_usage
                WHERE account_id = ? AND consumer_key = 'repo_bot' AND project_key = 'project_alpha'
                """,
                (account_id,),
            ).fetchone()
            self.assertIsNotNone(usage_row)
            self.assertGreaterEqual(usage_row["success_count"], 1)

    def test_complete_old_path_success_still_returns_used(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import pool as pool_repo

            account_id = self._insert_available_account(
                email="repo-old-path@example.com",
                pool_status="claimed",
                claim_token="clm_repo_old",
                claimed_by="repo_bot:repo_task_old",
                claimed_project_key=None,
            )

            db = get_db()
            new_status = pool_repo.complete(
                db,
                account_id=account_id,
                claim_token="clm_repo_old",
                caller_id="repo_bot",
                task_id="repo_task_old",
                result="success",
                detail="old path success",
            )
            self.assertEqual(new_status, "used")

    def test_complete_non_success_on_reuse_path_does_not_write_project_success(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import pool as pool_repo

            account_id = self._insert_available_account(
                email="repo-non-success@example.com",
                pool_status="claimed",
                claim_token="clm_repo_non_success",
                claimed_by="repo_bot:repo_task_non_success",
                claimed_project_key="project_alpha",
            )
            self._insert_usage_row(account_id=account_id, consumer_key="repo_bot", project_key="project_alpha")

            db = get_db()
            new_status = pool_repo.complete(
                db,
                account_id=account_id,
                claim_token="clm_repo_non_success",
                caller_id="repo_bot",
                task_id="repo_task_non_success",
                result="verification_timeout",
                detail="timeout path",
            )
            self.assertEqual(new_status, "cooldown")

            row = db.execute(
                """
                SELECT success_count, first_success_at, last_success_at
                FROM account_project_usage
                WHERE account_id = ? AND consumer_key = 'repo_bot' AND project_key = 'project_alpha'
                """,
                (account_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["success_count"], 0)
            self.assertIsNone(row["first_success_at"])
            self.assertIsNone(row["last_success_at"])

    def test_release_keeps_project_usage_row_but_clears_claimed_project_key(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import pool as pool_repo

            account_id = self._insert_available_account(
                email="repo-release@example.com",
                pool_status="claimed",
                claim_token="clm_repo_release",
                claimed_by="repo_bot:repo_task_5",
                claimed_project_key="project_alpha",
            )
            self._insert_usage_row(account_id=account_id, consumer_key="repo_bot", project_key="project_alpha")

            db = get_db()
            pool_repo.release(
                db,
                account_id=account_id,
                claim_token="clm_repo_release",
                caller_id="repo_bot",
                task_id="repo_task_5",
                reason="release test",
            )

            account_row = db.execute(
                "SELECT pool_status, claimed_project_key FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            self.assertEqual(account_row["pool_status"], "available")
            self.assertIsNone(account_row["claimed_project_key"])

            usage_row = db.execute(
                """
                SELECT id
                FROM account_project_usage
                WHERE account_id = ? AND consumer_key = 'repo_bot' AND project_key = 'project_alpha'
                """,
                (account_id,),
            ).fetchone()
            self.assertIsNotNone(usage_row)

    def test_expire_stale_claims_clears_claimed_project_key_without_creating_success_record(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import pool as pool_repo

            account_id = self._insert_available_account(
                email="repo-expire@example.com",
                pool_status="claimed",
                claim_token="clm_repo_expire",
                claimed_by="repo_bot:repo_task_expire",
                claimed_project_key="project_alpha",
                lease_expires_at="2000-01-01T00:00:00Z",
            )
            self._insert_usage_row(account_id=account_id, consumer_key="repo_bot", project_key="project_alpha")

            db = get_db()
            expired_count = pool_repo.expire_stale_claims(db)
            self.assertEqual(expired_count, 1)

            account_row = db.execute(
                "SELECT pool_status, claimed_project_key FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            self.assertEqual(account_row["pool_status"], "cooldown")
            self.assertIsNone(account_row["claimed_project_key"])

            usage_row = db.execute(
                """
                SELECT success_count
                FROM account_project_usage
                WHERE account_id = ? AND consumer_key = 'repo_bot' AND project_key = 'project_alpha'
                """,
                (account_id,),
            ).fetchone()
            self.assertIsNotNone(usage_row)
            self.assertEqual(usage_row["success_count"], 0)

    def test_get_stats_counts_reuse_path_success_account_as_available_not_used(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import pool as pool_repo

            account_id = self._insert_available_account(
                email="repo-stats@example.com",
                pool_status="claimed",
                claim_token="clm_repo_stats",
                claimed_by="repo_bot:repo_task_stats",
                claimed_project_key="project_alpha",
            )

            db = get_db()
            new_status = pool_repo.complete(
                db,
                account_id=account_id,
                claim_token="clm_repo_stats",
                caller_id="repo_bot",
                task_id="repo_task_stats",
                result="success",
                detail="stats path",
            )
            self.assertEqual(new_status, "available")

            stats = pool_repo.get_stats(db)
            self.assertEqual(stats["pool_counts"]["used"], 0)
            self.assertGreaterEqual(stats["pool_counts"]["available"], 1)


if __name__ == "__main__":
    unittest.main()
