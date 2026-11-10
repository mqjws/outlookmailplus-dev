"""
BUG-06 验证脚本：生成临时邮箱后，当前选中邮箱不应被重置

测试步骤：
1. 打开应用，检查登录状态
2. 导航到临时邮箱页面
3. 如果有现有邮箱，选中第一个
4. 记录 currentAccount（JS 全局变量）
5. 点击「+ 创建」生成新邮箱
6. 等待生成完成
7. 再次读取 currentAccount，应该与步骤 4 一致
"""

import time

from playwright.sync_api import sync_playwright


def get_login_password():
    """从 .env 文件读取登录密码"""
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("LOGIN_PASSWORD="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def run():
    login_password = get_login_password()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 有头模式便于观察
        page = browser.new_page()

        print("[1] 打开应用...")
        page.goto("http://127.0.0.1:5000")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="tests/screenshots/bug06_01_home.png", full_page=True)
        print("    截图: bug06_01_home.png")

        # 检查是否需要登录
        login_form = page.locator("#loginForm, form[action*='login'], input[type='password']")
        if page.url.__contains__("login") or login_form.count() > 0:
            if not login_password:
                print("    ❌ 检测到登录页，但未能从 .env 读取 LOGIN_PASSWORD，测试中止")
                browser.close()
                return
            print(f"[1a] 检测到登录页，自动填入密码...")
            pwd_input = page.locator("input[type='password']").first
            pwd_input.fill(login_password)
            # 提交登录表单
            submit_btn = page.locator("button[type='submit'], input[type='submit']").first
            submit_btn.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1000)
            page.screenshot(path="tests/screenshots/bug06_01a_after_login.png", full_page=True)
            print("    登录完成，截图: bug06_01a_after_login.png")

        print("[2] 导航到临时邮箱页面...")
        # 找到临时邮箱导航按钮
        nav_btn = page.locator('.nav-item[data-page="temp-emails"]')
        if nav_btn.count() > 0:
            nav_btn.click()
        else:
            # 尝试通过 JS 导航
            page.evaluate("navigate('temp-emails')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path="tests/screenshots/bug06_02_temp_emails.png", full_page=True)
        print("    截图: bug06_02_temp_emails.png")

        # 检查是否有现有的临时邮箱
        account_cards = page.locator("#tempEmailContainer .account-card")
        card_count = account_cards.count()
        print(f"[3] 当前临时邮箱数量: {card_count}")

        if card_count == 0:
            print("    没有现有临时邮箱，先生成一个作为基准...")
            page.locator("button:has-text('+ 创建')").first.click()
            page.wait_for_timeout(3000)
            page.wait_for_load_state("networkidle")
            account_cards = page.locator("#tempEmailContainer .account-card")
            card_count = account_cards.count()
            print(f"    生成后邮箱数量: {card_count}")
            if card_count == 0:
                print("    ❌ 无法生成邮箱，测试中止")
                browser.close()
                return

        # 选中第一个邮箱
        first_card = account_cards.first
        first_email_el = first_card.locator(".account-email")
        first_email = first_email_el.inner_text().strip()
        print(f"[4] 点击选中第一个邮箱: {first_email}")
        first_card.click()
        page.wait_for_timeout(1000)

        # 读取 currentAccount
        current_before = page.evaluate("currentAccount")
        print(f"    选中后 currentAccount = {current_before!r}")
        page.screenshot(path="tests/screenshots/bug06_03_selected.png", full_page=True)
        print("    截图: bug06_03_selected.png")

        if current_before != first_email:
            print(f"    ⚠️  currentAccount ({current_before}) 与点击的邮箱 ({first_email}) 不匹配，请检查")

        # 生成新的临时邮箱
        print("[5] 点击「+ 创建」生成新临时邮箱...")
        create_btn = page.locator("button:has-text('+ 创建')").first
        create_btn.click()

        # 等待 Toast 消息（成功提示）
        try:
            page.wait_for_selector(".toast, .toast-success", timeout=8000)
            print("    检测到 Toast 提示")
        except:
            print("    未检测到 Toast，等待 3s...")
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

        page.screenshot(path="tests/screenshots/bug06_04_after_generate.png", full_page=True)
        print("    截图: bug06_04_after_generate.png")

        # 读取生成后的 currentAccount
        current_after = page.evaluate("currentAccount")
        print(f"[6] 生成后 currentAccount = {current_after!r}")

        new_card_count = page.locator("#tempEmailContainer .account-card").count()
        print(f"    生成后邮箱数量: {new_card_count}")

        # 判断结果
        print("\n" + "=" * 50)
        if current_after == current_before:
            print(f"✅ BUG-06 已修复！生成新邮箱前后 currentAccount 保持不变：{current_after!r}")
        elif current_after is None:
            print(f"❌ BUG-06 仍存在！生成后 currentAccount 被清空为 None")
            print(f"   预期: {current_before!r}")
        else:
            print(f"⚠️  currentAccount 发生变化（可能是预期行为，也可能是 Bug）")
            print(f"   生成前: {current_before!r}")
            print(f"   生成后: {current_after!r}")
        print("=" * 50)

        # 检查 active 卡片
        active_cards = page.locator("#tempEmailContainer .account-card.active")
        active_count = active_cards.count()
        if active_count > 0:
            active_email = active_cards.first.locator(".account-email").inner_text().strip()
            print(f"\n活跃卡片高亮: {active_email!r}")
            if active_email == current_before:
                print("✅ 卡片高亮状态也正确保持")
            else:
                print(f"⚠️  卡片高亮与 currentAccount 不一致（高亮: {active_email!r}, currentAccount: {current_after!r}）")
        else:
            print("\n⚠️  没有任何卡片处于 active 状态")

        page.wait_for_timeout(2000)
        browser.close()
        print("\n测试完成，截图已保存到 tests/screenshots/ 目录")


if __name__ == "__main__":
    import os

    os.makedirs("tests/screenshots", exist_ok=True)
    run()
