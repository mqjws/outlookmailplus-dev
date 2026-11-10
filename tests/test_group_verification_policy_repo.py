from __future__ import annotations

import inspect
import unittest
import uuid

from tests._import_app import clear_login_attempts, import_web_app_module


class GroupVerificationPolicyRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()

    def _group_columns(self) -> set[str]:
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            rows = db.execute("PRAGMA table_info(groups)").fetchall()
        return {str(r["name"]) for r in rows}

    def _assert_policy_columns_exist(self):
        expected = {
            "verification_code_length",
            "verification_code_regex",
            "verification_ai_enabled",
            "verification_ai_model",
        }
        cols = self._group_columns()
        missing = expected - cols
        self.assertFalse(missing, f"groups 表缺少策略字段: {sorted(missing)}")

    def test_groups_table_contains_verification_policy_columns(self):
        self._assert_policy_columns_exist()

    def test_add_group_signature_supports_policy_fields(self):
        from outlook_web.repositories import groups as groups_repo

        params = set(inspect.signature(groups_repo.add_group).parameters.keys())
        for name in [
            "verification_code_length",
            "verification_code_regex",
            "verification_ai_enabled",
            "verification_ai_model",
        ]:
            self.assertIn(name, params, f"add_group 缺少参数: {name}")

    def test_update_group_signature_supports_policy_fields(self):
        from outlook_web.repositories import groups as groups_repo

        params = set(inspect.signature(groups_repo.update_group).parameters.keys())
        for name in [
            "verification_code_length",
            "verification_code_regex",
            "verification_ai_enabled",
            "verification_ai_model",
        ]:
            self.assertIn(name, params, f"update_group 缺少参数: {name}")

    def test_new_group_has_policy_default_values(self):
        self._assert_policy_columns_exist()

        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import groups as groups_repo

            group_name = f"policy_repo_{uuid.uuid4().hex[:10]}"
            group_id = groups_repo.add_group(group_name, "", "#123456", "")
            self.assertIsNotNone(group_id, "分组创建失败")

            db = get_db()
            row = db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
            self.assertIsNotNone(row)

            self.assertEqual(row["verification_code_length"], "6-6")
            self.assertEqual(row["verification_code_regex"], "")
            self.assertIn(int(row["verification_ai_enabled"] or 0), (0, 1))
            self.assertEqual(int(row["verification_ai_enabled"] or 0), 0)
            self.assertEqual(row["verification_ai_model"], "")

    def test_normalize_group_policy_accepts_common_length_formats(self):
        from outlook_web.repositories import groups as groups_repo

        cases = {
            "6": "6-6",
            "4~8": "4-8",
            "4-8位": "4-8",
            "6 位": "6-6",
            " 4 ～ 8 位数 ": "4-8",
        }

        for raw, expected in cases.items():
            policy = groups_repo.normalize_group_verification_policy(
                verification_code_length=raw,
                verification_code_regex="",
                verification_ai_enabled=0,
                verification_ai_model="",
            )
            self.assertEqual(policy["verification_code_length"], expected)


if __name__ == "__main__":
    unittest.main()
