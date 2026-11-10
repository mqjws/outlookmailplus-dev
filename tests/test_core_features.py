import json
import unittest
import uuid
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class CoreFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app
        # 导入 graph_service 用于 mock
        from outlook_web.services import graph as graph_service

        cls.graph_service = graph_service

    def setUp(self):
        # 每个测试前清理登录限制记录，避免测试间互相影响
        with self.app.app_context():
            clear_login_attempts()

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("success"), True)
        return resp

    def test_logout_revokes_session(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/logout", follow_redirects=False)
        self.assertIn(resp.status_code, (301, 302))

        resp = client.get("/api/system/health")
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertEqual(data.get("need_login"), True)

    def test_group_crud_and_audit_trace_id(self):
        client = self.app.test_client()
        self._login(client)

        unique = uuid.uuid4().hex
        group_name = f"g_{unique}"

        create = client.post(
            "/api/groups",
            json={
                "name": group_name,
                "description": "desc",
                "color": "#123456",
                "proxy_url": "",
            },
        )
        self.assertEqual(create.status_code, 200)
        create_data = create.get_json()
        self.assertEqual(create_data.get("success"), True)
        group_id = create_data.get("group_id")
        self.assertIsInstance(group_id, int)

        create_trace_id = create.headers.get("X-Trace-Id")
        self.assertTrue(create_trace_id)

        audit = client.get("/api/audit-logs?resource_type=group&limit=200")
        self.assertEqual(audit.status_code, 200)
        audit_data = audit.get_json()
        self.assertEqual(audit_data.get("success"), True)
        logs = audit_data.get("logs") or []
        self.assertTrue(any(l.get("trace_id") == create_trace_id for l in logs))

        update = client.put(
            f"/api/groups/{group_id}",
            json={
                "name": group_name,
                "description": "desc2",
                "color": "#654321",
                "proxy_url": "",
            },
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.get_json().get("success"), True)

        delete = client.delete(f"/api/groups/{group_id}")
        self.assertEqual(delete.status_code, 200)
        self.assertEqual(delete.get_json().get("success"), True)

        # 删除后再次获取：应返回结构化 404，不再沿用 legacy 400
        get_after = client.get(f"/api/groups/{group_id}")
        self.assertEqual(get_after.status_code, 404)
        data = get_after.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "GROUP_NOT_FOUND")
        self.assertEqual(data["error"].get("message"), "分组不存在")

    def test_tag_crud_and_duplicate_name(self):
        client = self.app.test_client()
        self._login(client)

        unique = uuid.uuid4().hex
        tag_name = f"t_{unique}"

        create = client.post("/api/tags", json={"name": tag_name, "color": "#abcdef"})
        self.assertEqual(create.status_code, 200)
        data = create.get_json()
        self.assertEqual(data.get("success"), True)
        tag_id = data.get("tag", {}).get("id")
        self.assertIsInstance(tag_id, int)

        dup = client.post("/api/tags", json={"name": tag_name, "color": "#000000"})
        self.assertEqual(dup.status_code, 400)
        dup_data = dup.get_json()
        self.assertEqual(dup_data.get("success"), False)
        self.assertIsInstance(dup_data.get("error"), dict)
        self.assertEqual(dup_data["error"].get("message"), "标签名称已存在")

        listing = client.get("/api/tags")
        self.assertEqual(listing.status_code, 200)
        listing_data = listing.get_json()
        self.assertEqual(listing_data.get("success"), True)
        self.assertIn(tag_name, [t.get("name") for t in (listing_data.get("tags") or [])])

        delete = client.delete(f"/api/tags/{tag_id}")
        self.assertEqual(delete.status_code, 200)
        self.assertEqual(delete.get_json().get("success"), True)

    def test_export_verify_and_export_all_download_contains_account(self):
        client = self.app.test_client()
        self._login(client)

        unique = uuid.uuid4().hex
        email_addr = f"export_{unique}@example.com"
        client_id = "cid_" + unique
        refresh_token = "rt_" + unique

        conn = self.module.create_sqlite_connection()
        try:
            conn.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, group_id, remark, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (email_addr, "pw", client_id, refresh_token, 1, "", "active"),
            )
            conn.commit()
        finally:
            conn.close()

        verify = client.post("/api/export/verify", json={"password": "testpass123"})
        self.assertEqual(verify.status_code, 200)
        verify_data = verify.get_json()
        self.assertEqual(verify_data.get("success"), True)
        verify_token = verify_data.get("verify_token")
        self.assertTrue(verify_token)

        # 使用请求头传递 token（避免 URL/日志泄露）
        export = client.get("/api/accounts/export", headers={"X-Export-Token": verify_token})
        self.assertEqual(export.status_code, 200)
        self.assertIn("text/plain", export.headers.get("Content-Type", ""))
        body = export.get_data(as_text=True)
        self.assertIn(email_addr, body)
        self.assertIn(client_id, body)
        self.assertIn(refresh_token, body)

        export_trace_id = export.headers.get("X-Trace-Id")
        self.assertTrue(export_trace_id)

        audit = client.get("/api/audit-logs?limit=200")
        self.assertEqual(audit.status_code, 200)
        audit_data = audit.get_json()
        self.assertEqual(audit_data.get("success"), True)
        logs = audit_data.get("logs") or []
        self.assertTrue(any(l.get("trace_id") == export_trace_id for l in logs))

    def test_temp_email_generate_and_list_mocked(self):
        client = self.app.test_client()
        self._login(client)

        email_addr = f"temp_{uuid.uuid4().hex}@example.com"
        # Mock legacy bridge 返回元组 (email_addr, None)
        # 当前正式入口经 temp mail provider 间接调用兼容 bridge，因此这里仍 patch gptmail 模块。
        from outlook_web.services import gptmail as gptmail_service

        with patch.object(gptmail_service, "generate_temp_email", return_value=(email_addr, None)):
            created = client.post("/api/temp-emails/generate", json={"prefix": "x", "domain": "y"})
        self.assertEqual(created.status_code, 200)
        created_data = created.get_json()
        self.assertEqual(created_data.get("success"), True)
        self.assertEqual(created_data.get("email"), email_addr)

        listing = client.get("/api/temp-emails")
        self.assertEqual(listing.status_code, 200)
        listing_data = listing.get_json()
        self.assertEqual(listing_data.get("success"), True)
        self.assertIn(email_addr, [e.get("email") for e in (listing_data.get("emails") or [])])

    def test_refresh_all_stream_has_start_and_complete_events(self):
        client = self.app.test_client()
        self._login(client)

        conn = self.module.create_sqlite_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                ("refresh_delay_seconds", "0"),
            )
            conn.commit()
        finally:
            conn.close()

        with patch.object(self.graph_service, "test_refresh_token_with_rotation", return_value=(True, None, None)):
            resp = client.get("/api/accounts/refresh-all")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))

        payload = resp.get_data(as_text=True)
        events = []
        for line in payload.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))

        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0].get("type"), "start")
        self.assertTrue(events[0].get("trace_id"))
        self.assertTrue(any(e.get("type") == "complete" for e in events))
