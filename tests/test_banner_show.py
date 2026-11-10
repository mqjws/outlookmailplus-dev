"""
测试环境验证：Banner 始终显示，截图供用户确认
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

        # 登录
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
        print("✅ 登录成功")

        # 等待 Banner 自动出现
        page.wait_for_timeout(3000)
        page.screenshot(path="screenshot_test_banner_top.png")
        print("\n✅ 截图已保存: screenshot_test_banner_top.png")

        # 检查结果
        banner = page.locator("#versionUpdateBanner")
        visible = banner.is_visible()
        print(f"\nBanner 可见: {visible}")

        if visible:
            msg = page.evaluate("""() => document.getElementById('versionUpdateMsg').innerText""")
            pos = page.evaluate("""() => window.getComputedStyle(document.getElementById('versionUpdateBanner')).position""")
            top = page.evaluate("""() => document.getElementById('versionUpdateBanner').getBoundingClientRect().top""")
            padding = page.evaluate("""() => document.getElementById('app').style.paddingTop""")
            btn_text = page.evaluate("""() => document.getElementById('btnTriggerUpdate').textContent""")
            btn_disabled = page.evaluate("""() => document.getElementById('btnTriggerUpdate').disabled""")

            print(f"  Banner 内容: {msg.strip()}")
            print(f"  position: {pos}")
            print(f"  距顶部: {top}px")
            print(f"  #app paddingTop: {padding}")
            print(f"  '立即更新'按钮文字: {btn_text}, disabled: {btn_disabled}")

            # 测试点击"忽略"
            print("\n====== 点击忽略 ======")
            page.locator("button >> text=忽略").first.click()
            page.wait_for_timeout(500)
            hidden = banner.is_hidden()
            pad_cleared = page.evaluate("""() => document.getElementById('app').style.paddingTop === ''""")
            print(f"  Banner 隐藏: {hidden}")
            print(f"  paddingTop 清除: {pad_cleared}")
            page.screenshot(path="screenshot_test_banner_dismissed.png")

            # 刷新页面，Banner 应重新出现
            print("\n====== 刷新页面 ======")
            page.reload()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)
            visible2 = banner.is_visible()
            print(f"  刷新后 Banner 重新显示: {visible2}")
            page.screenshot(path="screenshot_test_banner_reload.png")

        browser.close()


if __name__ == "__main__":
    main()
