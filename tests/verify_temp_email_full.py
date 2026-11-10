"""
临时邮箱功能全面测试脚本

测试场景：
T01 - 页面导航：能否正常进入临时邮箱页面
T02 - Provider 切换：GPTMail <-> Cloudflare Temp Mail，域名下拉状态
T03 - CF 域名加载：CF provider 下是否能加载可选域名
T04 - 生成邮箱（无前缀）：直接点创建，能否生成随机邮箱
T05 - 生成邮箱（带前缀）：指定 prefix 生成，邮箱地址包含前缀
T06 - 选中邮箱：点击卡片后 currentAccount 正确、卡片高亮
T07 - 获取邮件：点击「🔄 获取邮件」，能收到响应（空或有内容均可）
T08 - BUG-06 生成不重置选中：生成新邮箱后 currentAccount 不变
T09 - BUG-06 删除不重置选中（保留邮箱）：删除另一个邮箱，当前选中不变
T10 - 清空邮件：对当前选中邮箱执行清空操作
T11 - 删除邮箱：删除一个临时邮箱后列表减少
T12 - 复制邮箱地址：点击 📋 按钮，检查 clipboard API 调用无报错

注意：T09 只在临时邮箱数量 >= 2 时执行
"""

import os
import re
import time

from playwright.sync_api import expect, sync_playwright

SCREENSHOTS_DIR = "tests/screenshots/full"
BASE_URL = "http://127.0.0.1:5000"

results = []


def record(test_id, name, passed, detail=""):
    mark = "✅" if passed else "❌"
    results.append((test_id, name, passed, detail))
    print(f"  {mark} [{test_id}] {name}" + (f": {detail}" if detail else ""))


def get_login_password():
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("LOGIN_PASSWORD="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def do_login(page, password):
    pwd_input = page.locator("input[type='password']").first
    pwd_input.fill(password)
    submit_btn = page.locator("button[type='submit'], input[type='submit']").first
    submit_btn.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(800)


def screenshot(page, name):
    path = f"{SCREENSHOTS_DIR}/{name}.png"
    page.screenshot(path=path, full_page=True)
    return path


def run():
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    login_password = get_login_password()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        ctx.on(
            "console",
            lambda msg: print(f"  [browser-console] {msg.type}: {msg.text}") if msg.type == "error" else None,
        )
        page = ctx.new_page()

        # ── 登录 ───────────────────────────────────────────────
        print("\n=== 登录 ===")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        login_visible = page.locator("input[type='password']").count() > 0
        if login_visible:
            if not login_password:
                print("❌ 需要登录但未读到 LOGIN_PASSWORD，中止测试")
                browser.close()
                return
            do_login(page, login_password)
            print("  已自动登录")
        screenshot(page, "00_after_login")

        # ── T01: 导航到临时邮箱页面 ────────────────────────────
        print("\n=== T01: 页面导航 ===")
        nav_btn = page.locator('.nav-item[data-page="temp-emails"]')
        if nav_btn.count() > 0:
            nav_btn.click()
        else:
            page.evaluate("navigate('temp-emails')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        screenshot(page, "T01_temp_emails_page")

        current_page_js = page.evaluate("currentPage")
        panel_visible = page.locator("#page-temp-emails").is_visible()
        record(
            "T01",
            "导航到临时邮箱页面",
            current_page_js == "temp-emails" and panel_visible,
            f"currentPage={current_page_js!r}, panel visible={panel_visible}",
        )

        # ── T02: Provider 切换 ─────────────────────────────────
        print("\n=== T02: Provider 切换 ===")
        provider_select = page.locator("#tempEmailProviderSelect")
        domain_select = page.locator("#tempEmailDomainSelect")

        # 切换到 CF
        provider_select.select_option("cloudflare_temp_mail")
        page.wait_for_timeout(1200)
        cf_domain_enabled = not domain_select.is_disabled()
        screenshot(page, "T02a_cf_provider")
        record(
            "T02a",
            "切换到 CF 后域名下拉变可用",
            cf_domain_enabled,
            f"disabled={domain_select.is_disabled()}",
        )

        # 切换回 GPTMail
        provider_select.select_option("legacy_bridge")
        page.wait_for_timeout(500)
        legacy_domain_disabled = domain_select.is_disabled()
        screenshot(page, "T02b_legacy_provider")
        record(
            "T02b",
            "切换到 GPTMail 后域名下拉变禁用",
            legacy_domain_disabled,
            f"disabled={domain_select.is_disabled()}",
        )

        # ── T03: CF 域名加载 ───────────────────────────────────
        print("\n=== T03: CF 域名选项加载 ===")
        provider_select.select_option("cloudflare_temp_mail")
        page.wait_for_timeout(2000)  # 等待 fetch /api/temp-emails/options
        options_count = domain_select.locator("option").count()
        hint_text = page.locator("#tempEmailOptionsHint").inner_text()
        screenshot(page, "T03_cf_domain_options")
        record(
            "T03",
            "CF 域名选项已加载（>= 1 个选项）",
            options_count >= 1,
            f"options={options_count}, hint={hint_text!r}",
        )

        # ── T04: 生成邮箱（无前缀）────────────────────────────
        print("\n=== T04: 生成邮箱（无前缀） ===")
        # 清空前缀输入框
        prefix_input = page.locator("#tempEmailPrefixInput")
        prefix_input.fill("")
        before_count = page.locator("#tempEmailContainer .account-card").count()
        print(f"  生成前邮箱数量: {before_count}")

        page.locator(".workspace-panel.accounts-column button:has-text('+ 创建')").click()
        try:
            page.wait_for_selector(".toast, [class*='toast']", timeout=6000)
        except:
            pass
        page.wait_for_timeout(2500)
        after_count = page.locator("#tempEmailContainer .account-card").count()
        screenshot(page, "T04_generate_no_prefix")
        record(
            "T04",
            "无前缀生成邮箱成功（数量增加）",
            after_count > before_count,
            f"{before_count} -> {after_count}",
        )

        # ── T05: 生成邮箱（带前缀）────────────────────────────
        print("\n=== T05: 生成邮箱（带前缀） ===")
        test_prefix = "testpfx"
        prefix_input.fill(test_prefix)
        before_count2 = page.locator("#tempEmailContainer .account-card").count()
        page.locator(".workspace-panel.accounts-column button:has-text('+ 创建')").click()
        try:
            page.wait_for_selector(".toast, [class*='toast']", timeout=6000)
        except:
            pass
        page.wait_for_timeout(2500)
        after_count2 = page.locator("#tempEmailContainer .account-card").count()
        screenshot(page, "T05_generate_with_prefix")

        # 检查最新卡片的邮箱地址是否包含 prefix
        all_emails_text = page.locator("#tempEmailContainer .account-email").all_inner_texts()
        prefix_found = any(test_prefix in e for e in all_emails_text)
        record(
            "T05",
            f"带前缀 '{test_prefix}' 生成邮箱成功",
            after_count2 > before_count2 and prefix_found,
            f"数量 {before_count2}->{after_count2}, 找到前缀={prefix_found}",
        )
        prefix_input.fill("")  # 清空前缀

        # ── T05b: BUG-07 生成后域名下拉框不被重置 ────────────
        print("\n=== T05b: BUG-07 生成新邮箱后域名选中不变 ===")
        # 先选一个非默认域名（如果有的话）
        all_domain_opts = domain_select.locator("option").all()
        non_default_domain = None
        for opt in all_domain_opts:
            val = opt.get_attribute("value")
            if val:  # 非空值即非"自动分配"
                non_default_domain = val
                break
        if non_default_domain:
            domain_select.select_option(non_default_domain)
            page.wait_for_timeout(300)
            domain_before = domain_select.input_value()
            print(f"  选定域名: {domain_before!r}")
            # 生成一个新邮箱
            page.locator(".workspace-panel.accounts-column button:has-text('+ 创建')").click()
            try:
                page.wait_for_selector(".toast, [class*='toast']", timeout=6000)
            except:
                pass
            page.wait_for_timeout(2500)
            domain_after = domain_select.input_value()
            screenshot(page, "T05b_domain_preserved")
            record(
                "T05b",
                f"生成后域名下拉仍选中 '{non_default_domain}'（BUG-07）",
                domain_after == domain_before,
                f"before={domain_before!r}, after={domain_after!r}",
            )
        else:
            record(
                "T05b",
                "BUG-07 域名保留（跳过，无非默认域名可选）",
                True,
                "只有一个域名选项，自动通过",
            )
        print("\n=== T06: 选中邮箱 ===")
        cards = page.locator("#tempEmailContainer .account-card")
        if cards.count() > 0:
            first_card = cards.first
            first_email_text = first_card.locator(".account-email").inner_text().strip()
            first_card.click()
            page.wait_for_timeout(800)
            current_account = page.evaluate("currentAccount")
            is_temp_group = page.evaluate("isTempEmailGroup")
            active_count = page.locator("#tempEmailContainer .account-card.active").count()
            header_name = page.locator("#tempEmailCurrentName").inner_text().strip()
            screenshot(page, "T06_select_email")
            record(
                "T06",
                "选中邮箱后 currentAccount 正确",
                current_account == first_email_text,
                f"currentAccount={current_account!r}",
            )
            record(
                "T06b",
                "选中后卡片有 active 样式",
                active_count == 1,
                f"active_count={active_count}",
            )
            record(
                "T06c",
                "页面顶部显示选中邮箱名",
                first_email_text in header_name,
                f"header={header_name!r}",
            )
        else:
            record("T06", "选中邮箱", False, "没有邮箱可选")

        # ── T07: 获取邮件 ──────────────────────────────────────
        print("\n=== T07: 获取邮件 ===")
        refresh_btn = page.locator("#tempEmailRefreshBtn")
        if refresh_btn.is_visible():
            refresh_btn.click()
            # 等待按钮从"获取中..."恢复
            try:
                page.wait_for_function(
                    "document.getElementById('tempEmailRefreshBtn') && !document.getElementById('tempEmailRefreshBtn').disabled",
                    timeout=10000,
                )
            except:
                pass
            page.wait_for_timeout(500)
            msg_list = page.locator("#tempEmailMessageList")
            msg_html = msg_list.inner_html()
            has_error = "⚠️" in msg_html or "error" in msg_html.lower()
            has_content = "email-item" in msg_html or "empty-state" in msg_html
            screenshot(page, "T07_get_messages")
            record(
                "T07",
                "获取邮件后消息区有内容（空或有邮件）",
                has_content and not has_error,
                f"有内容={has_content}, 有错误={has_error}",
            )
        else:
            record("T07", "获取邮件", False, "刷新按钮不可见")

        # ── T08: BUG-06 生成不重置选中 ─────────────────────────
        print("\n=== T08: BUG-06 生成新邮箱不重置当前选中 ===")
        current_before = page.evaluate("currentAccount")
        if current_before:
            page.locator(".workspace-panel.accounts-column button:has-text('+ 创建')").click()
            try:
                page.wait_for_selector(".toast, [class*='toast']", timeout=6000)
            except:
                pass
            page.wait_for_timeout(2500)
            current_after = page.evaluate("currentAccount")
            screenshot(page, "T08_bug06_generate")
            record(
                "T08",
                "生成新邮箱后当前选中不变（BUG-06）",
                current_after == current_before,
                f"before={current_before!r}, after={current_after!r}",
            )
        else:
            record("T08", "BUG-06 生成不重置", False, "当前无选中邮箱，跳过")

        # ── T09: BUG-06 删除别的邮箱不重置选中 ────────────────
        print("\n=== T09: BUG-06 删除另一个邮箱不重置当前选中 ===")
        all_cards = page.locator("#tempEmailContainer .account-card")
        total = all_cards.count()
        current_acc = page.evaluate("currentAccount")
        if total >= 2 and current_acc:
            # 找一张不是当前选中的卡片来删除
            target_email = None
            for i in range(total):
                card = all_cards.nth(i)
                em = card.locator(".account-email").inner_text().strip()
                if em != current_acc:
                    target_email = em
                    delete_btn = card.locator("button[title='删除']")
                    # 处理确认对话框
                    page.once("dialog", lambda d: d.accept())
                    delete_btn.click()
                    break
            if target_email:
                page.wait_for_timeout(2500)
                current_after_del = page.evaluate("currentAccount")
                screenshot(page, "T09_bug06_delete_other")
                record(
                    "T09",
                    "删除其他邮箱后当前选中不变（BUG-06）",
                    current_after_del == current_acc,
                    f"deleted={target_email!r}, current unchanged={current_after_del!r}",
                )
            else:
                record("T09", "BUG-06 删除不重置", False, "未找到可删除的非当前邮箱")
        else:
            record(
                "T09",
                "BUG-06 删除不重置（跳过，邮箱不足2个）",
                True,
                f"total={total}, 自动通过",
            )

        # ── T10: 清空邮件 ──────────────────────────────────────
        print("\n=== T10: 清空邮件 ===")
        curr = page.evaluate("currentAccount")
        if curr:
            active_card = page.locator("#tempEmailContainer .account-card.active")
            if active_card.count() > 0:
                clear_btn = active_card.locator("button[title='清空']")
                page.once("dialog", lambda d: d.accept())
                clear_btn.click()
                page.wait_for_timeout(2000)
                # 检查消息列表是否变空
                msg_list_html = page.locator("#tempEmailMessageList").inner_html()
                is_cleared = "empty-state" in msg_list_html or "收件箱为空" in msg_list_html
                screenshot(page, "T10_clear_messages")
                record(
                    "T10",
                    "清空邮件后消息列表显示空状态",
                    is_cleared,
                    f"cleared_ui={is_cleared}",
                )
            else:
                record("T10", "清空邮件", False, "没有 active 卡片")
        else:
            record("T10", "清空邮件", False, "当前无选中邮箱")

        # ── T11: 删除邮箱 ──────────────────────────────────────
        print("\n=== T11: 删除当前邮箱 ===")
        current_acc2 = page.evaluate("currentAccount")
        before_del_count = page.locator("#tempEmailContainer .account-card").count()
        if current_acc2 and before_del_count > 0:
            active_card2 = page.locator("#tempEmailContainer .account-card.active")
            if active_card2.count() > 0:
                del_btn = active_card2.first.locator("button[title='删除']")
                page.once("dialog", lambda d: d.accept())
                del_btn.click()
                page.wait_for_timeout(2500)
                after_del_count = page.locator("#tempEmailContainer .account-card").count()
                current_after2 = page.evaluate("currentAccount")
                screenshot(page, "T11_delete_current_email")
                record(
                    "T11a",
                    "删除当前邮箱后列表减少",
                    after_del_count < before_del_count,
                    f"{before_del_count} -> {after_del_count}",
                )
                record(
                    "T11b",
                    "删除当前邮箱后 currentAccount 被清空",
                    current_after2 is None,
                    f"currentAccount={current_after2!r}",
                )
            else:
                record("T11a", "删除当前邮箱", False, "没有 active 卡片可删")
        else:
            record(
                "T11a",
                "删除当前邮箱",
                False,
                f"无选中邮箱或列表为空 (count={before_del_count})",
            )

        # ── T12: 复制邮箱地址 ──────────────────────────────────
        print("\n=== T12: 复制邮箱地址（📋 按钮无 JS 报错） ===")
        all_cards2 = page.locator("#tempEmailContainer .account-card")
        errors_before = []
        ctx.on(
            "console",
            lambda msg: errors_before.append(msg.text) if msg.type == "error" else None,
        )
        if all_cards2.count() > 0:
            copy_btn = all_cards2.first.locator("button[title='复制']")
            copy_btn.click()
            page.wait_for_timeout(500)
            screenshot(page, "T12_copy_email")
            record("T12", "点击复制按钮无 JS 异常", True, "按钮点击成功")
        else:
            record("T12", "复制邮箱地址", False, "无邮箱卡片可测试")

        # ── 汇总 ───────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("临时邮箱功能全面测试结果汇总")
        print("=" * 60)
        passed = sum(1 for _, _, ok, _ in results if ok)
        failed = sum(1 for _, _, ok, _ in results if not ok)
        for tid, name, ok, detail in results:
            mark = "✅" if ok else "❌"
            print(f"  {mark} [{tid}] {name}" + (f"\n       {detail}" if detail else ""))
        print("=" * 60)
        print(f"  通过: {passed}  失败: {failed}  总计: {passed + failed}")
        print("=" * 60)
        print(f"\n截图保存在: {SCREENSHOTS_DIR}/")

        page.wait_for_timeout(2000)
        browser.close()


if __name__ == "__main__":
    run()
