from __future__ import annotations

import unittest

from tests._import_app import import_web_app_module


class GroupPolicyFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def _get_text(self, client, path: str) -> str:
        resp = client.get(path)
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()

    def test_modals_contains_group_policy_fields(self):
        client = self.app.test_client()
        self._login(client)
        html = self._get_text(client, "/")

        self.assertIn('id="groupVerificationCodeLength"', html)
        self.assertIn('id="groupVerificationCodeRegex"', html)
        self.assertNotIn('id="groupVerificationAiEnabled"', html)
        self.assertNotIn('id="groupVerificationAiModel"', html)

    def test_groups_js_contains_group_policy_read_and_write(self):
        client = self.app.test_client()
        js = self._get_text(client, "/static/js/features/groups.js")

        # 编辑回填
        self.assertIn("groupVerificationCodeLength", js)
        self.assertIn("groupVerificationCodeRegex", js)
        self.assertNotIn("groupVerificationAiEnabled", js)
        self.assertNotIn("groupVerificationAiModel", js)

        # 保存 payload
        self.assertIn("verification_code_length", js)
        self.assertIn("verification_code_regex", js)
        self.assertNotIn("verification_ai_enabled", js)
        self.assertNotIn("verification_ai_model", js)


if __name__ == "__main__":
    unittest.main()
