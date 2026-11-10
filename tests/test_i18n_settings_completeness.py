"""tests/test_i18n_settings_completeness.py — 设置页 i18n 词条完整性测试

验证 static/js/i18n.js 的 exactMap 中包含设置页所需的全部中英映射。
对应 TD: docs/TD/2026-04-12-设置页i18n缺失补齐-TD.md
"""

from __future__ import annotations

import re
import unittest

from tests._import_app import import_web_app_module


class SettingsI18nCompletenessTests(unittest.TestCase):
    """确保设置页中文文案在 exactMap 中有对应英文翻译"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _get_i18n_js(self):
        client = self.app.test_client()
        resp = client.get("/static/js/i18n.js")
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()

    def _assert_exact_map_entry(self, js: str, zh_key: str, en_value: str):
        """验证 exactMap 中存在 zh_key -> en_value 的映射"""
        # exactMap 中的格式: '中文key': 'English value',
        pattern = re.escape(zh_key) + r"'\s*:\s*'" + re.escape(en_value)
        self.assertRegex(
            js,
            pattern,
            f"exactMap 中应包含映射: '{zh_key}' -> '{en_value}'",
        )

    # ── AI 增强配置区 ──

    def test_basic_settings_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(js, "基础设置", "Basic Settings")

    def test_basic_settings_with_emoji_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(js, "⚙️ 基础设置", "⚙️ Basic Settings")

    def test_ai_enhancement_no_space_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(js, "验证码AI增强", "Verification Code AI Enhancement")

    def test_ai_enhancement_with_emoji_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(js, "🤖 验证码 AI 增强", "🤖 Verification Code AI Enhancement")

    def test_ai_enhancement_toggle_no_space_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(
            js, "启用验证码AI增强（系统级）", "Enable Verification Code AI Enhancement (System-level)"
        )

    def test_ai_enhancement_toggle_with_space_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(
            js, "启用验证码 AI 增强（系统级）", "Enable Verification Code AI Enhancement (System-level)"
        )

    def test_ai_fallback_rule_no_space_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(
            js,
            "规则提取优先；仅在规则不足时触发AI回退。",
            "Rule extraction first; trigger AI fallback only when rules are insufficient.",
        )

    def test_ai_fallback_rule_with_space_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(
            js,
            "规则提取优先；仅在规则不足时触发 AI 回退。",
            "Rule extraction first; trigger AI fallback only when rules are insufficient.",
        )

    def test_ai_model_id_no_space_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(js, "AI模型ID", "AI Model ID")

    def test_ai_model_id_with_space_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(js, "AI 模型 ID", "AI Model ID")

    def test_test_ai_config_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(js, "测试 AI 配置", "Test AI Configuration")

    def test_test_ai_config_with_emoji_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(js, "🤖 测试 AI 配置", "🤖 Test AI Configuration")

    def test_save_before_test_hint_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(js, "建议先保存配置再测试。", "Save settings before testing is recommended.")

    # ── 临时邮箱 Provider 描述 ──

    def test_self_hosted_provider_desc_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(js, "自建域名临时邮箱服务", "Self-hosted custom-domain temp mailbox service")

    def test_cf_worker_provider_desc_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(js, "CF Worker 部署的临时邮箱", "Temp mailbox powered by CF Worker deployment")

    # ── CF Worker 域名同步区 ──

    def test_cf_sync_hint_short_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(
            js,
            "自动读取 CF Worker 的域名配置，同步至下方域名字段。",
            "Automatically read CF Worker domain configuration and sync to the domain fields below.",
        )

    def test_cf_sync_hint_long_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(
            js,
            "自动读取 CF Worker 的域名配置，同步至下方「临时邮箱可用域名」和「默认域名」。",
            'Automatically read the CF Worker domain configuration and sync to the "Available Domains" and "Default Domain" fields below.',
        )

    def test_available_domains_readonly_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(
            js, "可用域名（只读 · 通过同步按钮更新）", "Available domains (read-only · updated via sync button)"
        )

    def test_default_domain_readonly_has_translation(self):
        js = self._get_i18n_js()
        self._assert_exact_map_entry(
            js, "默认域名（只读 · 通过同步按钮更新）", "Default domain (read-only · updated via sync button)"
        )

    # ── 变体一致性 ──

    def test_ai_enhancement_variants_share_same_translation(self):
        """无空格/有emoji两种变体应映射到相同的英文翻译（仅 emoji 不同）"""
        js = self._get_i18n_js()
        # 提取两个映射的值，确认核心翻译一致
        pattern_no_emoji = r"'验证码AI增强'\s*:\s*'([^']+)'"
        pattern_with_emoji = r"'🤖 验证码 AI 增强'\s*:\s*'([^']+)'"
        match1 = re.search(pattern_no_emoji, js)
        match2 = re.search(pattern_with_emoji, js)
        self.assertIsNotNone(match1, "应存在 '验证码AI增强' 映射")
        self.assertIsNotNone(match2, "应存在 '🤖 验证码 AI 增强' 映射")
        # 核心翻译应一致（一个带 emoji 前缀，一个不带）
        self.assertEqual(
            match1.group(1).replace("🤖 ", ""),
            match2.group(1).replace("🤖 ", ""),
            "两种变体的核心英文翻译应一致",
        )


if __name__ == "__main__":
    unittest.main()
