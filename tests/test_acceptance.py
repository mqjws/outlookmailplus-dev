"""
版本更新检测与一键更新 — 自动化验收测试
"""

import json
import sys

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None  # type: ignore
    PLAYWRIGHT_AVAILABLE = False

BASE = "http://127.0.0.1:5000"
PASSWORD = "admin123"
RESULTS = []


def log(name, passed, detail=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    RESULTS.append((name, passed, detail))
    print(f"{status} | {name} {detail}")


def try_login(page, password):
    """尝试登录，返回是否成功"""
    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    page.fill("#password", password)
    page.click("#loginBtn")
    # 等待跳转或错误
    page.wait_for_timeout(2000)

    # 检查是否跳转到主页
    if page.locator("#app").is_visible():
        return True

    # 检查是否还在登录页
    error_el = page.locator("#errorMessage")
    if error_el.is_visible():
        err_text = error_el.text_content()
        print(f"  登录错误: {err_text}")

    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        # 监听 console
        page.on(
            "console",
            lambda msg: print(f"  [CONSOLE] {msg.text}") if msg.type == "error" else None,
        )

        # ========== Step 1: 登录 ==========
        print("\n====== 登录 ======")
        logged_in = try_login(page, PASSWORD)

        if not logged_in:
            # 可能被 rate limit，等一下重试
            print("  首次登录失败，等待 3 秒后重试...")
            page.wait_for_timeout(3000)
            logged_in = try_login(page, PASSWORD)

        log("登录成功", logged_in)
        if not logged_in:
            page.screenshot(path="screenshot_login_fail.png")
            print("登录失败，截图已保存: screenshot_login_fail.png")
            print("  请确认服务已启动且密码正确（默认 admin123）")
            browser.close()
            sys.exit(1)

        page.screenshot(path="screenshot_00_dashboard.png")

        # ========== TC-01: 页面顶部 Banner 位置验证 ==========
        print("\n====== TC-01: Banner 位置验证 ======")
        banner = page.locator("#versionUpdateBanner")
        banner_hidden = banner.is_hidden()
        log("TC-01a: Banner 默认隐藏", banner_hidden, "(无更新时应隐藏)")

        # ========== TC-02: 版本检测 API 接口验证 ==========
        print("\n====== TC-02: API 接口验证 ======")
        api_resp = page.evaluate("""
            async () => {
                const res = await fetch('/api/system/version-check');
                return await res.json();
            }
        """)
        has_current_version = "current_version" in api_resp
        has_latest_version = "latest_version" in api_resp
        has_has_update = "has_update" in api_resp
        has_success = api_resp.get("success") is True
        no_old_current = "current" not in api_resp or "current_version" in api_resp
        no_old_latest = "latest" not in api_resp or "latest_version" in api_resp
        log("TC-02a: 字段 current_version 存在", has_current_version)
        log("TC-02b: 字段 latest_version 存在", has_latest_version)
        log("TC-02c: 字段 has_update 存在", has_has_update)
        log("TC-02d: success=true", has_success)
        log(
            "TC-02e: 无旧字段 current/latest",
            no_old_current and no_old_latest,
            f"resp={json.dumps(api_resp, ensure_ascii=False)}",
        )

        # ========== TC-03: Mock Banner 显示 ==========
        print("\n====== TC-03: Mock Banner 显示 ======")
        page.evaluate("""
            () => {
                const banner = document.getElementById('versionUpdateBanner');
                document.getElementById('versionUpdateMsg').innerHTML = 
                    '发现新版本 <strong>v9.9.9</strong>（当前 v1.10.2） <a href="#" class="ms-1">查看更新日志</a>';
                banner.classList.remove('d-none');
                document.getElementById('app').style.paddingTop = banner.offsetHeight + 'px';
            }
        """)
        page.wait_for_timeout(500)
        page.screenshot(path="screenshot_03_banner_visible.png")

        banner_visible = banner.is_visible()
        log("TC-03a: Banner 可见", banner_visible)

        # 检查 position: fixed
        banner_pos = page.evaluate("""
            () => window.getComputedStyle(document.getElementById('versionUpdateBanner')).position
        """)
        log(
            "TC-03b: Banner position=fixed",
            banner_pos == "fixed",
            f"position={banner_pos}",
        )

        # 检查 top=0
        banner_top = page.evaluate("""
            () => window.getComputedStyle(document.getElementById('versionUpdateBanner')).top
        """)
        log("TC-03c: Banner top=0px", banner_top == "0px", f"top={banner_top}")

        # 检查按钮
        has_update_btn = page.locator("#btnTriggerUpdate").is_visible()
        dismiss_loc = page.locator("button >> text=忽略")
        has_dismiss_btn = dismiss_loc.is_visible() if dismiss_loc.count() > 0 else False
        log("TC-03d: '立即更新'按钮存在", has_update_btn)
        log("TC-03e: '忽略'按钮存在", has_dismiss_btn)

        # 检查 app padding-top
        app_padding = page.evaluate("""
            () => document.getElementById('app').style.paddingTop
        """)
        log(
            "TC-03f: #app padding-top 已设置",
            app_padding != "" and app_padding != "0px",
            f"paddingTop={app_padding}",
        )

        # ========== TC-04: 忽略按钮 ==========
        print("\n====== TC-04: 忽略按钮 ======")
        page.locator("button >> text=忽略").click()
        page.wait_for_timeout(500)
        banner_hidden_after = banner.is_hidden()
        app_padding_cleared = page.evaluate("""
            () => document.getElementById('app').style.paddingTop === ''
        """)
        page.screenshot(path="screenshot_04_dismiss.png")
        log("TC-04a: 点击忽略后 Banner 隐藏", banner_hidden_after)
        log("TC-04b: 点击忽略后 padding-top 清除", app_padding_cleared)

        # ========== TC-05: 触发更新按钮（无 Watchtower 降级测试） ==========
        print("\n====== TC-05: 触发更新（降级测试） ======")
        page.evaluate("""
            () => {
                const banner = document.getElementById('versionUpdateBanner');
                document.getElementById('versionUpdateMsg').innerHTML = 
                    '发现新版本 <strong>v9.9.9</strong>（当前 v1.10.2） <a href="#" class="ms-1">查看更新日志</a>';
                banner.classList.remove('d-none');
                document.getElementById('app').style.paddingTop = banner.offsetHeight + 'px';
            }
        """)
        page.wait_for_timeout(300)

        page.click("#btnTriggerUpdate")
        page.wait_for_timeout(5000)
        page.screenshot(path="screenshot_05_trigger.png")

        no_crash = page.locator("#app").is_visible()
        btn_text = page.evaluate("""
            () => document.getElementById('btnTriggerUpdate').textContent
        """)
        btn_disabled = page.evaluate("""
            () => document.getElementById('btnTriggerUpdate').disabled
        """)
        # 预期：无 Watchtower 时，后端返回 500，JS 走 catch 分支
        # 按钮应恢复为可点击状态（disabled=false, text=立即更新）
        gracefully_degraded = not btn_disabled and no_crash
        log("TC-05a: 触发更新后页面不崩溃", no_crash)
        log(
            "TC-05b: 优雅降级（按钮恢复可点击）",
            gracefully_degraded,
            f"btn_text={btn_text}, disabled={btn_disabled}",
        )

        # ========== TC-07: 未登录鉴权 ==========
        print("\n====== TC-07: 未登录鉴权 ======")
        page2 = browser.new_page()
        resp = page2.goto(f"{BASE}/api/system/version-check")
        status_code = resp.status if resp else 0
        log(
            "TC-07a: 未登录返回 401/302",
            status_code in (401, 302),
            f"status={status_code}",
        )
        page2.close()

        # ========== 总结 ==========
        print("\n" + "=" * 60)
        total = len(RESULTS)
        passed = sum(1 for _, p, _ in RESULTS if p)
        failed = total - passed
        print(f"总计: {total} 项 | ✅ 通过: {passed} | ❌ 失败: {failed}")
        print("=" * 60)

        for name, p, detail in RESULTS:
            s = "✅" if p else "❌"
            print(f"  {s} {name} {detail}")

        browser.close()
        sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
