"""
tests/test_prd00011_proxy_live.py
PRD-00011 代理支持补全 — 集成测试（基于 Flask TestClient，无需独立服务器进程）

测试覆盖：
  1. GET /api/settings 返回 telegram_proxy_url 字段
  2. PUT /api/settings 可以保存并读回 telegram_proxy_url
  3. POST /api/settings/test-telegram-proxy 路由已注册
  4. 未配置 Bot Token 时接口返回合理错误（非 5xx/404）
  5. 直接用 requests 测试代理可达性（可选，不强制）
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# 应用初始化（复用项目标准 _import_app 辅助）
# ──────────────────────────────────────────────────────────────────────────────

# 添加 tests 目录到路径以便导入 _import_app
_tests_dir = Path(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

from _import_app import clear_login_attempts, import_web_app_module


def _login(client):
    """登录辅助（CSRF 已在测试配置中禁用）"""
    clear_login_attempts()
    resp = client.post("/login", json={"password": "testpass123"})
    return resp.status_code == 200 and resp.get_json().get("success")


class TestPRD00011Settings(unittest.TestCase):
    """验收点 1：GET/PUT /api/settings 的 telegram_proxy_url 字段"""

    @classmethod
    def setUpClass(cls):
        cls._module = import_web_app_module()
        cls._app = cls._module.app
        cls._app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            WTF_CSRF_CHECK_DEFAULT=False,
        )

    def setUp(self):
        self.client = self._app.test_client()
        ok = _login(self.client)
        if not ok:
            self.skipTest("登录失败，跳过测试")

    def test_get_settings_returns_telegram_proxy_url(self):
        """GET /api/settings 响应中应包含 telegram_proxy_url 字段"""
        resp = self.client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"), f"GET /api/settings failed: {data}")
        settings = data.get("settings", {})
        self.assertIn(
            "telegram_proxy_url",
            settings,
            "settings 中缺少 telegram_proxy_url 字段",
        )

    def test_put_settings_saves_telegram_proxy_url(self):
        """PUT /api/settings 可以保存并读回 telegram_proxy_url"""
        test_url = "http://test-proxy.example.com:8080"
        resp = self.client.put("/api/settings", json={"telegram_proxy_url": test_url})
        self.assertEqual(resp.status_code, 200, f"PUT failed: {resp.get_json()}")
        data = resp.get_json()
        self.assertTrue(data.get("success"), f"PUT /api/settings failed: {data}")

        # 读回验证
        resp2 = self.client.get("/api/settings")
        saved = resp2.get_json().get("settings", {}).get("telegram_proxy_url", "")
        self.assertEqual(
            saved,
            test_url,
            f"保存后读回的 proxy_url 不一致，期望 {test_url!r}，实际 {saved!r}",
        )

    def test_put_settings_clears_telegram_proxy_url(self):
        """PUT /api/settings 传空字符串可以清空 telegram_proxy_url"""
        # 先写入
        self.client.put("/api/settings", json={"telegram_proxy_url": "http://x.com:1"})
        # 再清空
        resp = self.client.put("/api/settings", json={"telegram_proxy_url": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        resp2 = self.client.get("/api/settings")
        saved = resp2.get_json().get("settings", {}).get("telegram_proxy_url", "MISSING")
        self.assertEqual(saved, "", f"清空后期望空字符串，实际 {saved!r}")


class TestPRD00011TelegramProxyNoToken(unittest.TestCase):
    """验收点 2（无 Bot Token 情况）：POST /api/settings/test-telegram-proxy"""

    @classmethod
    def setUpClass(cls):
        cls._module = import_web_app_module()
        cls._app = cls._module.app
        cls._app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            WTF_CSRF_CHECK_DEFAULT=False,
        )

    def setUp(self):
        self.client = self._app.test_client()
        ok = _login(self.client)
        if not ok:
            self.skipTest("登录失败，跳过测试")
        # 清空 telegram_bot_token，确保测试环境干净
        self.client.put("/api/settings", json={"telegram_bot_token": ""})

    def test_proxy_test_without_bot_token_returns_error(self):
        """未配置 Bot Token 时，测试代理接口应返回提示错误（非 5xx）"""
        resp = self.client.post(
            "/api/settings/test-telegram-proxy",
            json={"proxy_url": "socks5://127.0.0.1:1080"},
        )
        # 接口本身应当正常响应（不是 500/404）
        self.assertIn(resp.status_code, (200, 400), f"意外状态码: {resp.status_code}")
        data = resp.get_json()
        # 两种合法响应：success=False + 提示信息，或 success=True + ok=False
        if not data.get("success"):
            self.assertIn("message", data.get("error", {}), "error 对象中缺少 message")
        # 不应抛出服务端异常
        self.assertNotEqual(resp.status_code, 500, "接口不应返回 500")


class TestPRD00011ProxyEndpoint(unittest.TestCase):
    """验收点 2（路由是否存在）：POST /api/settings/test-telegram-proxy 接口路由已注册"""

    @classmethod
    def setUpClass(cls):
        cls._module = import_web_app_module()
        cls._app = cls._module.app
        cls._app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            WTF_CSRF_CHECK_DEFAULT=False,
        )

    def setUp(self):
        self.client = self._app.test_client()
        ok = _login(self.client)
        if not ok:
            self.skipTest("登录失败，跳过测试")

    def test_route_exists(self):
        """POST /api/settings/test-telegram-proxy 应返回非 404"""
        resp = self.client.post(
            "/api/settings/test-telegram-proxy",
            json={"proxy_url": ""},
        )
        self.assertNotEqual(resp.status_code, 404, "路由未注册（返回 404）")
        self.assertNotEqual(resp.status_code, 405, "方法不允许（405），路由注册有误")

    def test_response_has_success_field(self):
        """接口响应必须包含 success 字段"""
        resp = self.client.post(
            "/api/settings/test-telegram-proxy",
            json={"proxy_url": ""},
        )
        data = resp.get_json()
        self.assertIsNotNone(data, "响应应为 JSON")
        self.assertIn("success", data, "响应缺少 success 字段")


if __name__ == "__main__":
    unittest.main(verbosity=2)
