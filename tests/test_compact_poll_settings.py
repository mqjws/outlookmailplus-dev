import unittest

from tests._import_app import clear_login_attempts, import_web_app_module


class CompactPollSettingsTests(unittest.TestCase):
    """A 类：后端 Settings API 契约测试 — 简洁模式自动轮询配置项"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db

            # TC-A07 需要验证这三个 key 不在 DB 中（DB 层不预置默认值）
            # 其他测试通过 GET Python fallback 默认值（10/5）或 PUT API 设置值
            db = get_db()
            db.execute(
                "DELETE FROM settings WHERE key IN "
                "('enable_compact_auto_poll', 'compact_poll_interval', 'compact_poll_max_count')"
            )
            db.commit()

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    # TC-A01: GET 返回默认值
    def test_get_settings_returns_compact_poll_defaults(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        settings = resp.get_json().get("settings", {})
        self.assertFalse(settings.get("enable_compact_auto_poll", True))
        self.assertEqual(settings.get("compact_poll_interval"), 10)
        self.assertEqual(settings.get("compact_poll_max_count"), 5)

    # TC-A02: PUT + GET 回环
    def test_put_get_round_trip(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={
                "enable_compact_auto_poll": True,
                "compact_poll_interval": 15,
                "compact_poll_max_count": 10,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        resp2 = client.get("/api/settings")
        self.assertEqual(resp2.status_code, 200)
        settings = resp2.get_json().get("settings", {})
        self.assertTrue(settings.get("enable_compact_auto_poll"))
        self.assertEqual(settings.get("compact_poll_interval"), 15)
        self.assertEqual(settings.get("compact_poll_max_count"), 10)

    # TC-A03: enable 非 bool 拒绝
    def test_reject_invalid_enable_value(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={"enable_compact_auto_poll": "yes"},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("简洁模式自动轮询开关", data.get("error", {}).get("message", ""))

    # TC-A04: interval 范围 3-60
    def test_interval_boundary_values(self):
        client = self.app.test_client()
        self._login(client)

        # 小于下限 3 应拒绝
        resp = client.put(
            "/api/settings",
            json={"compact_poll_interval": 2},
        )
        self.assertEqual(resp.status_code, 400)

        # 大于上限 60 应拒绝
        resp = client.put(
            "/api/settings",
            json={"compact_poll_interval": 61},
        )
        self.assertEqual(resp.status_code, 400)

        # 边界 3 应通过
        resp = client.put(
            "/api/settings",
            json={"compact_poll_interval": 3},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        # 边界 60 应通过
        resp = client.put(
            "/api/settings",
            json={"compact_poll_interval": 60},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    # TC-A05: max_count 范围 0-100
    def test_max_count_boundary_values(self):
        client = self.app.test_client()
        self._login(client)

        # 小于下限 0 应拒绝
        resp = client.put(
            "/api/settings",
            json={"compact_poll_max_count": -1},
        )
        self.assertEqual(resp.status_code, 400)

        # 大于上限 100 应拒绝
        resp = client.put(
            "/api/settings",
            json={"compact_poll_max_count": 101},
        )
        self.assertEqual(resp.status_code, 400)

        # 边界 0 应通过（表示持续轮询）
        resp = client.put(
            "/api/settings",
            json={"compact_poll_max_count": 0},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        # 边界 100 应通过
        resp = client.put(
            "/api/settings",
            json={"compact_poll_max_count": 100},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    # TC-A06: 非数字值拒绝
    def test_reject_non_numeric_values(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={"compact_poll_interval": "abc"},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("数字", data.get("error", {}).get("message", ""))

    # TC-A07: DB 默认值
    def test_db_default_values(self):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            self.assertEqual(settings_repo.get_setting("enable_compact_auto_poll", None), None)
            self.assertEqual(settings_repo.get_setting("compact_poll_interval", None), None)
            self.assertEqual(settings_repo.get_setting("compact_poll_max_count", None), None)

    # TC-A08: 字符串 "false"
    def test_put_false_then_get_returns_false(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={"enable_compact_auto_poll": False},
        )
        self.assertEqual(resp.status_code, 200)

        resp2 = client.get("/api/settings")
        settings = resp2.get_json().get("settings", {})
        self.assertFalse(settings.get("enable_compact_auto_poll"))

    # TC-A09: 与标准轮询隔离
    def test_compact_poll_isolated_from_standard_polling(self):
        client = self.app.test_client()
        self._login(client)

        # 先设置标准轮询值
        client.put(
            "/api/settings",
            json={
                "enable_auto_polling": True,
                "polling_interval": 20,
                "polling_count": 10,
            },
        )

        # 再修改简洁轮询设置
        resp = client.put(
            "/api/settings",
            json={
                "enable_compact_auto_poll": True,
                "compact_poll_interval": 5,
                "compact_poll_max_count": 8,
            },
        )
        self.assertEqual(resp.status_code, 200)

        # 标准轮询值应保持不变
        resp2 = client.get("/api/settings")
        settings = resp2.get_json().get("settings", {})
        self.assertTrue(settings.get("enable_auto_polling"))
        self.assertEqual(settings.get("polling_interval"), 20)
        self.assertEqual(settings.get("polling_count"), 10)

    # TC-A10: 部分字段更新
    def test_partial_update_preserves_defaults(self):
        client = self.app.test_client()
        self._login(client)

        # 只更新 enable，不传 interval 和 max_count
        resp = client.put(
            "/api/settings",
            json={"enable_compact_auto_poll": True},
        )
        self.assertEqual(resp.status_code, 200)

        resp2 = client.get("/api/settings")
        settings = resp2.get_json().get("settings", {})
        self.assertTrue(settings.get("enable_compact_auto_poll"))
        # interval 和 max_count 应保持默认值
        self.assertEqual(settings.get("compact_poll_interval"), 10)
        self.assertEqual(settings.get("compact_poll_max_count"), 5)

    # TC-A11: updated 列表
    def test_put_returns_updated_list(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings",
            json={
                "enable_compact_auto_poll": True,
                "compact_poll_interval": 8,
                "compact_poll_max_count": 15,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        message = data.get("message", "")
        self.assertIn("简洁轮询开关", message)
        self.assertIn("简洁轮询间隔", message)
        self.assertIn("简洁轮询次数", message)

    # TC-A12: 未登录拒绝
    def test_unauthenticated_get_rejected(self):
        client = self.app.test_client()

        resp = client.get("/api/settings")
        # 未登录时应返回非 200（302 重定向或 401）
        self.assertNotEqual(resp.status_code, 200)
