from __future__ import annotations

"""
UI/UX v2 前端契约测试 — 覆盖 pool_admin.js 新增功能与 i18n 完整性

TDD: docs/TDD/2026-05-18-Issue60-号池管理UI与状态维护TDD.md
PRD: docs/PRD/2026-05-18-Issue60-号池管理UI与状态维护PRD.md
FD:  docs/FD/2026-05-18-Issue60-号池管理UI与状态维护FD.md

测试目标：
1. pool_admin.js 声明了 v2 新增函数 (renderCell, actionLink, buildPagination, 批量选择)
2. i18n.js 包含号池管理所有翻译条目（exactMap + regex patterns）
3. i18n.js 未丢失已有翻译条目（回归保护：账号批量删除确认框）
4. main.css 包含 Pool Admin 表格增强样式
5. index.html 包含 toolbar 布局 + 批量操作区 DOM
"""

import re
import unittest

from tests._import_app import import_web_app_module


class PoolAdminUIv2Base(unittest.TestCase):
    """UI/UX v2 契约测试基类"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app
        cls.client = cls.app.test_client()

    def _get_js(self, path: str) -> str:
        resp = self.client.get(path)
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()

    def _get_html(self, path: str) -> str:
        resp = self.client.get(path)
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()

    def _login(self):
        resp = self.client.post("/login", json={"password": "testpass123"})
        if resp.status_code != 200:
            raise RuntimeError(f"登录失败 ({resp.status_code})")

    def _assert_exact_map_entry(self, js: str, zh_key: str, en_value: str):
        pattern = re.escape(zh_key) + r"'\s*:\s*'" + re.escape(en_value)
        self.assertRegex(js, pattern, f"exactMap 应包含 '{zh_key}' -> '{en_value}'")

    def _assert_pattern_entry(self, js: str, zh_pattern: str, en_template: str):
        self.assertIn(zh_pattern, js, f"patterns 中应包含中文正则: {zh_pattern}")
        self.assertIn(en_template, js, f"patterns 中应包含英文模板: {en_template}")


# ===== 1. pool_admin.js 新增函数声明 =====


class PoolAdminJsV2FunctionTests(PoolAdminUIv2Base):
    """pool_admin.js UI/UX v2 新增函数声明测试"""

    def setUp(self):
        self.js = self._get_js("/static/js/features/pool_admin.js")

    def test_declares_render_cell(self):
        """应声明 renderCell 空数据弱化函数"""
        self.assertIn("function renderCell", self.js)

    def test_declares_action_link(self):
        """应声明 actionLink 文字链接函数"""
        self.assertIn("function actionLink", self.js)

    def test_declares_build_pagination(self):
        """应声明 buildPagination 省略号分页函数"""
        self.assertIn("function buildPagination", self.js)

    def test_declares_toggle_row(self):
        """应声明 togglePoolAdminRow 单行选择函数"""
        self.assertIn("function togglePoolAdminRow", self.js)

    def test_declares_toggle_all(self):
        """应声明 togglePoolAdminAll 全选函数"""
        self.assertIn("function togglePoolAdminAll", self.js)

    def test_declares_update_batch_bar(self):
        """应声明 updatePoolAdminBatchBar 批量操作栏更新函数"""
        self.assertIn("function updatePoolAdminBatchBar", self.js)

    def test_declares_batch_action(self):
        """应声明 batchPoolAdminAction 批量操作函数"""
        self.assertIn("function batchPoolAdminAction", self.js)

    def test_declares_selected_ids_state(self):
        """状态对象应包含 selectedIds 集合"""
        self.assertIn("selectedIds", self.js)
        self.assertIn("new Set()", self.js)

    def test_uses_data_table_enhanced_css(self):
        """应使用增强表格 CSS 类 data-table--pool-admin"""
        self.assertIn("data-table--pool-admin", self.js)

    def test_uses_pa_row_check_class(self):
        """行 checkbox 应使用 pa-row-check 类"""
        self.assertIn("pa-row-check", self.js)

    def test_uses_pool_admin_toolbar_class(self):
        """应引用 pool-admin-toolbar CSS 类（index.html 中定义）"""
        self._login()
        self.assertIn("pool-admin-toolbar", self._get_html("/"))

    def test_batch_action_serial_strategy(self):
        """批量操作应采用逐条串行策略（doNext 递归）"""
        self.assertIn("doNext", self.js)
        self.assertIn("doNext();", self.js)

    def test_confirm_uses_whole_sentence_translation(self):
        """确认框应使用整句翻译而非分片拼接
        业务规则 (TDD): 避免中英语序差异导致 "Selected20条" 问题"""
        self.assertIn("确定对 ", self.js)
        self.assertNotIn("确定对}", self.js)

    def test_pagination_uses_delta_1(self):
        """分页器 delta 应为 1（当前页前后各 1 页）"""
        self.assertIn("const delta = 1", self.js)

    def test_render_cell_checks_null_and_empty(self):
        """renderCell 应检查 null/undefined/空/NULL"""
        self.assertIn("text === null", self.js)
        self.assertIn("text === 'NULL'", self.js)

    def test_action_link_uses_anchor_not_button(self):
        """actionLink 应输出 <a> 标签而非 <button>"""
        self.assertIn('<a href="javascript:void(0)"', self.js)

    def test_claimed_only_shows_force_release(self):
        """claimed 状态行只应展示 force_release 操作
        业务规则 (TDD/C-01~C-04)"""
        self.assertIn("isClaimed", self.js)
        self.assertIn("force_release", self.js)


# ===== 2. i18n exactMap 完整性 =====


class PoolAdminI18nExactMapTests(PoolAdminUIv2Base):
    """号池管理 i18n exactMap 翻译完整性测试"""

    def setUp(self):
        self.js = self._get_js("/static/js/i18n.js")

    def test_pool_admin_card_title(self):
        self._assert_exact_map_entry(self.js, "🎱 号池管理", "🎱 Pool Admin")

    def test_pool_admin_title_no_emoji(self):
        self._assert_exact_map_entry(self.js, "号池管理", "Pool Admin")

    def test_batch_move_in(self):
        self._assert_exact_map_entry(self.js, "批量移入", "Bulk Move In")

    def test_batch_move_out(self):
        self._assert_exact_map_entry(self.js, "批量移出", "Bulk Move Out")

    def test_selected(self):
        self._assert_exact_map_entry(self.js, "已选", "Selected")

    def test_type_label(self):
        self._assert_exact_map_entry(self.js, "类型", "Type")

    def test_pool_status_label(self):
        self._assert_exact_map_entry(self.js, "池状态", "Pool Status")

    def test_last_result_label(self):
        self._assert_exact_map_entry(self.js, "最近结果", "Last Result")

    def test_actions_label(self):
        self._assert_exact_map_entry(self.js, "操作", "Actions")

    def test_search_placeholder(self):
        self._assert_exact_map_entry(self.js, "搜索邮箱…", "Search email...")

    def test_claimed_by(self):
        self._assert_exact_map_entry(self.js, "占用方", "Claimed by")

    def test_all_groups(self):
        self._assert_exact_map_entry(self.js, "所有分组", "All Groups")

    def test_records_unit(self):
        self._assert_exact_map_entry(self.js, "条记录", "records")

    def test_done_label(self):
        self._assert_exact_map_entry(self.js, "完成", "Done")

    def test_success_label(self):
        self._assert_exact_map_entry(self.js, "成功", "success")

    def test_failed_label(self):
        self._assert_exact_map_entry(self.js, "失败", "failed")

    def test_loading_label(self):
        self._assert_exact_map_entry(self.js, "加载中…", "Loading...")

    def test_no_data_label(self):
        self._assert_exact_map_entry(self.js, "暂无数据", "No data")

    def test_load_failed_label(self):
        self._assert_exact_map_entry(self.js, "加载失败", "Load failed")

    def test_request_failed_label(self):
        self._assert_exact_map_entry(self.js, "请求失败", "Request failed")

    def test_plugin_management_label(self):
        self._assert_exact_map_entry(self.js, "插件管理", "Plugin Management")

    def test_api_security_label(self):
        self._assert_exact_map_entry(self.js, "🔐 API 安全设置", "🔐 API Security Settings")


# ===== 3. i18n regex pattern 完整性 =====


class PoolAdminI18nPatternTests(PoolAdminUIv2Base):
    """号池管理 i18n regex pattern 翻译规则测试"""

    def setUp(self):
        self.js = self._get_js("/static/js/i18n.js")

    def test_pattern_selected_n(self):
        """已选 N 条 → $1 selected"""
        self._assert_pattern_entry(self.js, "^已选 (\\d+) 条$", "$1 selected")

    def test_pattern_total_page_info(self):
        """共 N 条 · 第 M/P 页 → Total $1 · Page $2/$3"""
        self._assert_pattern_entry(self.js, "^共 (\\d+) 条 · 第 (\\d+)\\/(\\d+) 页$", "Total $1 · Page $2/$3")

    def test_pattern_total_only(self):
        """共 N 条 → Total $1"""
        self._assert_pattern_entry(self.js, "^共 (\\d+) 条$", "Total $1")

    def test_pattern_batch_confirm(self):
        """确定对 N 条记录执行「…」吗？ → Confirm … on $1 records?"""
        self._assert_pattern_entry(self.js, "^确定对 (\\d+) 条记录执行「(.+)」吗？$", "Confirm $2 on $1 records?")

    def test_pattern_done_summary(self):
        """完成: N 成功, M 失败 → Done: $1 success, $2 failed"""
        self._assert_pattern_entry(self.js, "^完成: (\\d+) 成功, (\\d+) 失败$", "Done: $1 success, $2 failed")

    def test_pattern_single_confirm(self):
        """确定对 email 执行「…」吗？ → Confirm … on $1?"""
        self._assert_pattern_entry(self.js, "^确定对 (.+) 执行「(.+)」吗？$", "Confirm $2 on $1?")


# ===== 4. i18n 回归保护 =====


class PoolAdminI18nRegressionTests(PoolAdminUIv2Base):
    """确保号池管理变更未丢失已有翻译条目"""

    def setUp(self):
        self.js = self._get_js("/static/js/i18n.js")

    def test_account_bulk_delete_pattern_not_lost(self):
        """账号批量删除确认框翻译 pattern 不应被误删
        回归保护: main.js:4400 使用此 pattern"""
        self.assertIn(
            "确定要删除选中的 (\\d+) 个账号吗？此操作不可恢复！",
            self.js,
            "账号批量删除确认框 pattern 被误删",
        )
        self.assertIn(
            "Delete $1 selected accounts? This action cannot be undone.",
            self.js,
            "账号批量删除确认框英文模板被误删",
        )


# ===== 5. CSS 样式规则 =====


class PoolAdminCssTests(PoolAdminUIv2Base):
    """Pool Admin 表格增强 CSS 测试"""

    def setUp(self):
        self.css = self._get_js("/static/css/main.css")

    def test_data_table_pool_admin_header_style(self):
        """应存在 .data-table--pool-admin th 样式"""
        self.assertIn(".data-table--pool-admin th", self.css)

    def test_data_table_pool_admin_row_hover(self):
        """应存在行 hover 样式"""
        self.assertIn(".data-table--pool-admin tbody tr:hover", self.css)

    def test_toolbar_input_select_style(self):
        """应存在 toolbar 内 select/input 缩小样式"""
        self.assertIn(".pool-admin-toolbar select", self.css)
        self.assertIn(".pool-admin-toolbar input", self.css)


# ===== 6. index.html DOM 结构 =====


class PoolAdminDomStructureTests(PoolAdminUIv2Base):
    """index.html Pool Admin DOM 结构测试"""

    def setUp(self):
        self._login()
        self.html = self._get_html("/")

    def test_toolbar_class_exists(self):
        """应使用 pool-admin-toolbar 而非旧的 pool-admin-filters"""
        self.assertIn("pool-admin-toolbar", self.html)

    def test_old_filter_class_removed(self):
        """旧的 pool-admin-filters 类应已移除"""
        self.assertNotIn("pool-admin-filters", self.html)

    def test_batch_bar_exists(self):
        """应存在批量操作栏 DOM"""
        self.assertIn("poolAdminBatchBar", self.html)
        self.assertIn("poolAdminBatchCount", self.html)

    def test_batch_move_buttons_exist(self):
        """应存在批量移入和批量移出按钮"""
        self.assertIn("batchPoolAdminAction('move_into_pool')", self.html)
        self.assertIn("batchPoolAdminAction('move_out_of_pool')", self.html)

    def test_search_placeholder_compact(self):
        """搜索框 placeholder 应简化为 '搜索邮箱…'"""
        self.assertIn("搜索邮箱…", self.html)

    def test_flex_spacer_exists(self):
        """工具栏应有弹性空白区域分隔筛选和批量操作"""
        self.assertIn("flex:1", self.html)


if __name__ == "__main__":
    unittest.main()
