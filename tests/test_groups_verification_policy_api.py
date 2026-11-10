from __future__ import annotations

import unittest
import uuid

from tests._import_app import clear_login_attempts, import_web_app_module


class GroupsVerificationPolicyApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def _create_group(self, client, **overrides) -> int:
        payload = {
            "name": f"group_{uuid.uuid4().hex[:10]}",
            "description": "",
            "color": "#123456",
            "proxy_url": "",
        }
        payload.update(overrides)
        resp = client.post("/api/groups", json=payload)
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body.get("success"), body)
        return int(body["group_id"])

    def test_create_group_with_policy_fields_success(self):
        client = self.app.test_client()
        self._login(client)

        gid = self._create_group(
            client,
            verification_code_length="4-8",
            verification_code_regex=r"\b\d{6}\b",
        )

        detail = client.get(f"/api/groups/{gid}")
        self.assertEqual(detail.status_code, 200)
        group = detail.get_json().get("group", {})
        self.assertEqual(group.get("verification_code_length"), "4-8")
        self.assertEqual(group.get("verification_code_regex"), r"\b\d{6}\b")
        self.assertEqual(int(group.get("verification_ai_enabled") or 0), 0)
        self.assertEqual(group.get("verification_ai_model"), "")

    def test_update_group_with_policy_fields_success(self):
        client = self.app.test_client()
        self._login(client)
        gid = self._create_group(client)

        resp = client.put(
            f"/api/groups/{gid}",
            json={
                "name": f"upd_{uuid.uuid4().hex[:8]}",
                "description": "desc",
                "color": "#654321",
                "proxy_url": "",
                "verification_code_length": "6-6",
                "verification_code_regex": r"\b[A-Z0-9]{6}\b",
                "verification_ai_enabled": 1,
                "verification_ai_model": "gpt-4.1-mini",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        detail = client.get(f"/api/groups/{gid}")
        self.assertEqual(detail.status_code, 200)
        group = detail.get_json().get("group", {})
        self.assertEqual(group.get("verification_code_length"), "6-6")
        self.assertEqual(group.get("verification_code_regex"), r"\b[A-Z0-9]{6}\b")
        self.assertEqual(int(group.get("verification_ai_enabled") or 0), 0)
        self.assertEqual(group.get("verification_ai_model"), "")

    def test_invalid_code_length_returns_error(self):
        client = self.app.test_client()
        self._login(client)
        gid = self._create_group(client)

        resp = client.put(
            f"/api/groups/{gid}",
            json={
                "name": f"upd_{uuid.uuid4().hex[:8]}",
                "description": "",
                "color": "#111111",
                "proxy_url": "",
                "verification_code_length": "abc",
                "verification_code_regex": "",
                "verification_ai_enabled": 0,
                "verification_ai_model": "",
            },
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertFalse(body.get("success"))
        self.assertEqual((body.get("error") or {}).get("code"), "GROUP_VERIFICATION_LENGTH_INVALID")

    def test_update_group_accepts_single_length_input(self):
        client = self.app.test_client()
        self._login(client)
        gid = self._create_group(client)

        resp = client.put(
            f"/api/groups/{gid}",
            json={
                "name": f"upd_{uuid.uuid4().hex[:8]}",
                "description": "",
                "color": "#111111",
                "proxy_url": "",
                "verification_code_length": "6",
                "verification_code_regex": "",
                "verification_ai_enabled": 0,
                "verification_ai_model": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        detail = client.get(f"/api/groups/{gid}")
        self.assertEqual(detail.status_code, 200)
        group = detail.get_json().get("group", {})
        self.assertEqual(group.get("verification_code_length"), "6-6")

    def test_update_group_accepts_tilde_length_input(self):
        client = self.app.test_client()
        self._login(client)
        gid = self._create_group(client)

        resp = client.put(
            f"/api/groups/{gid}",
            json={
                "name": f"upd_{uuid.uuid4().hex[:8]}",
                "description": "",
                "color": "#111111",
                "proxy_url": "",
                "verification_code_length": "4~8",
                "verification_code_regex": "",
                "verification_ai_enabled": 0,
                "verification_ai_model": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        detail = client.get(f"/api/groups/{gid}")
        self.assertEqual(detail.status_code, 200)
        group = detail.get_json().get("group", {})
        self.assertEqual(group.get("verification_code_length"), "4-8")

    def test_invalid_code_regex_returns_error(self):
        client = self.app.test_client()
        self._login(client)
        gid = self._create_group(client)

        resp = client.put(
            f"/api/groups/{gid}",
            json={
                "name": f"upd_{uuid.uuid4().hex[:8]}",
                "description": "",
                "color": "#111111",
                "proxy_url": "",
                "verification_code_length": "6-6",
                "verification_code_regex": "[unclosed",
                "verification_ai_enabled": 0,
                "verification_ai_model": "",
            },
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertFalse(body.get("success"))
        self.assertEqual((body.get("error") or {}).get("code"), "GROUP_VERIFICATION_REGEX_INVALID")

    def test_ai_fields_in_payload_are_soft_ignored(self):
        client = self.app.test_client()
        self._login(client)
        gid = self._create_group(client)

        resp = client.put(
            f"/api/groups/{gid}",
            json={
                "name": f"upd_{uuid.uuid4().hex[:8]}",
                "description": "",
                "color": "#111111",
                "proxy_url": "",
                "verification_code_length": "6-6",
                "verification_code_regex": "",
                "verification_ai_enabled": 1,
                "verification_ai_model": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        detail = client.get(f"/api/groups/{gid}")
        self.assertEqual(detail.status_code, 200)
        group = detail.get_json().get("group", {})
        self.assertEqual(int(group.get("verification_ai_enabled") or 0), 0)
        self.assertEqual(group.get("verification_ai_model"), "")


if __name__ == "__main__":
    unittest.main()
