"""
TC-01 真实验证：用 Playwright route mock API → 页面加载后 Banner 自动显示
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


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        page.on("console", lambda msg: print(f"  [CONSOLE {msg.type}] {msg.text}"))

        # ========== Route intercept: mock version-check API ==========
        def handle_route(route):
            if "version-check" in route.request.url:
                mock_data = {
                    "success": True,
                    "has_update": True,
                    "current_version": "0.0.1",
                    "latest_version": "9.9.9",
                    "release_url": "https://github.com/hshaokang/outlookemail-plus/releases/tag/v9.9.9",
                }
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(mock_data),
                )
            else:
                route.continue_()

        page.route("**/api/system/version-check", handle_route)

        # ========== 登录 ==========
        print("====== 登录 ======")
        page.goto(BASE)
        page.wait_for_load_state("networkidle")
        page.fill("#password", PASSWORD)
        page.click("#loginBtn")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        if not page.locator("#app").is_visible():
            print("❌ 登录失败")
            browser.close()
            sys.exit(1)
        print("✅ 登录成功，已进入主页")

        # ========== 等待 checkVersionUpdate 执行完 ==========
        print("\n====== 等待 Banner 自动显示 ======")
        page.wait_for_timeout(3000)

        page.screenshot(path="screenshot_tc01_auto_banner.png")

        # ========== 检查结果 ==========
        banner = page.locator("#versionUpdateBanner")
        banner_visible = banner.is_visible()
        print(f"  Banner 自动显示: {banner_visible}")

        if banner_visible:
            msg_html = page.evaluate("""
                () => document.getElementById('versionUpdateMsg').innerHTML
            """)
            print(f"  Banner 内容: {msg_html.strip()}")

            banner_pos = page.evaluate("""
                () => window.getComputedStyle(document.getElementById('versionUpdateBanner')).position
            """)
            banner_rect_top = page.evaluate("""
                () => document.getElementById('versionUpdateBanner').getBoundingClientRect().top
            """)
            app_padding = page.evaluate("""
                () => document.getElementById('app').style.paddingTop
            """)
            has_update_btn = page.locator("#btnTriggerUpdate").is_visible()
            has_dismiss = page.locator("button >> text=忽略").first.is_visible()

            print(f"  Banner position: {banner_pos}")
            print(f"  Banner 距顶部: {banner_rect_top}px")
            print(f"  #app paddingTop: {app_padding}")
            print(f"  '立即更新'按钮: {has_update_btn}")
            print(f"  '忽略'按钮: {has_dismiss}")
        else:
            banner_class = page.evaluate("""
                () => document.getElementById('versionUpdateBanner').className
            """)
            print(f"  Banner class: {banner_class}")
            print("  ❌ Banner 没有自动显示")

        # ========== 忽略按钮测试 ==========
        if banner_visible:
            print("\n====== 测试忽略按钮 ======")
            page.locator("button >> text=忽略").first.click()
            page.wait_for_timeout(500)
            banner_hidden = banner.is_hidden()
            app_padding_cleared = page.evaluate("""
                () => document.getElementById('app').style.paddingTop === ''
            """)
            print(f"  点击忽略后 Banner 隐藏: {banner_hidden}")
            print(f"  点击忽略后 paddingTop 清除: {app_padding_cleared}")

        # ========== 总结 ==========
        print("\n====== 总结 ======")
        if banner_visible:
            print("✅ TC-01 通过: 检测到新版本时，页面加载后 Banner 自动显示在页面顶部")
        else:
            print("❌ TC-01 失败: API 返回 has_update=true 但 Banner 未自动显示")

        browser.close()


if __name__ == "__main__":
    main()
