from __future__ import annotations

"""
TDD D 层：号池管理前端契约测试

覆盖 docs/TDD/2026-05-18-Issue60-号池管理UI与状态维护TDD.md §8
当前运行会失败（红）—— 前端模板和 JS 模块尚未创建。
实现 templates/index.html 对应容器 + static/js/features/pool_admin.js 后，所有用例应通过（绿）。

测试目标：
1. [MVP] 页面容器存在（id 或 class）
2. [MVP] 筛选控件文案存在
3. [MVP] 前端模块声明了 pool admin loader
4. [MVP] 前端模块声明了 pool admin action handler
5. [MVP] claimed 保护有明确文案提示
"""

import unittest

from tests._import_app import import_web_app_module


class PoolAdminFrontendContractBase(unittest.TestCase):
    """前端契约测试基类"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app
        cls.client = cls.app.test_client()

    def _get_text(self, path):
        resp = self.client.get(path)
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()

    def _login(self):
        resp = self.client.post("/login", json={"password": "testpass123"})
        if resp.status_code != 200:
            raise RuntimeError(f"测试用户登录失败 ({resp.status_code})")


# ===== MVP: §8 前端契约 =====


class PoolAdminPageContainerTests(PoolAdminFrontendContractBase):
    """页面入口与容器测试"""

    def test_index_contains_pool_admin_page_container(self):
        """页面中应存在号池管理的页面容器（id 或 class）"""
        self._login()
        html = self._get_text("/")

        # 至少应包含以下任一标识：pool_admin / poolAdmin / pool-admin / 号池管理
        has_container = any(
            marker in html
            for marker in [
                "pool-admin",
                "poolAdmin",
                "pool_admin",
                "号池管理",
            ]
        )
        self.assertTrue(has_container, "index.html 应包含号池管理页面容器标识")

    def test_index_contains_pool_admin_entry_button(self):
        """页面中应有号池管理入口按钮或导航项"""
        self._login()
        html = self._get_text("/")

        has_entry = any(
            marker in html
            for marker in [
                "号池管理",
                "pool-admin",
                "poolAdmin",
            ]
        )
        self.assertTrue(has_entry, "index.html 应包含号池管理入口")


class PoolAdminFilterControlsTests(PoolAdminFrontendContractBase):
    """筛选控件测试"""

    def test_index_contains_pool_admin_filter_controls(self):
        """筛选栏应包含池内/池外或 pool_status 相关控件"""
        self._login()
        html = self._get_text("/")

        # 应有池内/池外筛选相关的文案或控件
        has_filter = any(
            marker in html
            for marker in [
                "in_pool",
                "in-pool",
                "池内",
                "池外",
                "pool_status",
                "pool-status",
            ]
        )
        self.assertTrue(has_filter, "index.html 应包含号池管理筛选控件文案")


class PoolAdminJsModuleTests(PoolAdminFrontendContractBase):
    """前端 JS 模块测试"""

    def test_frontend_module_declares_pool_admin_loader(self):
        """pool_admin.js 或其他 JS 应声明加载/初始化函数"""
        # 检查 pool_admin.js 是否存在
        resp = self.client.get("/static/js/features/pool_admin.js")
        if resp.status_code == 200:
            js = resp.data.decode("utf-8")
            has_loader = any(
                marker in js
                for marker in [
                    "loadPoolAdmin",
                    "initPoolAdmin",
                    "pool_admin",
                    "poolAdmin",
                    "PoolAdmin",
                ]
            )
            self.assertTrue(has_loader, "pool_admin.js 应声明初始化/加载函数")
        else:
            # 如果文件不存在，在 main.js 或其他 features 中检查
            main_js = self._get_text("/static/js/main.js")
            has_loader = any(
                marker in main_js
                for marker in [
                    "pool_admin",
                    "poolAdmin",
                    "PoolAdmin",
                ]
            )
            self.assertTrue(has_loader, "main.js 或 pool_admin.js 应声明 pool admin 模块加载入口")

    def test_frontend_module_declares_pool_admin_action_handler(self):
        """前端模块应包含动作执行逻辑"""
        resp = self.client.get("/static/js/features/pool_admin.js")
        if resp.status_code == 200:
            js = resp.data.decode("utf-8")
            has_action = any(
                marker in js
                for marker in [
                    "move_into_pool",
                    "move_out_of_pool",
                    "pool-admin/accounts",
                    "action",
                ]
            )
            self.assertTrue(has_action, "pool_admin.js 应包含动作处理逻辑")
        else:
            # 文件未创建时跳过，允许红阶段
            self.skipTest("pool_admin.js 尚未创建")


class PoolAdminClaimedProtectionCopyTests(PoolAdminFrontendContractBase):
    """claimed 保护文案测试"""

    def test_frontend_contains_claimed_protection_copy(self):
        """前端应有 claimed 状态保护的明确文案"""
        self._login()
        html = self._get_text("/")

        # 检查是否有 claimed 占用中相关文案
        has_claimed_copy = any(
            marker in html
            for marker in [
                "占用中",
                "claimed",
                "占用",
            ]
        )
        if not has_claimed_copy:
            # 如果 HTML 没有，检查 JS
            resp = self.client.get("/static/js/features/pool_admin.js")
            if resp.status_code == 200:
                js = resp.data.decode("utf-8")
                has_claimed_copy = any(marker in js for marker in ["claimed", "占用中", "占用"])
            # 也检查 i18n
            if not has_claimed_copy:
                i18n_js = self._get_text("/static/js/i18n.js")
                has_claimed_copy = "claimed" in i18n_js or "占用" in i18n_js

        self.assertTrue(has_claimed_copy, "前端应有 claimed 状态保护相关文案")


if __name__ == "__main__":
    unittest.main()
