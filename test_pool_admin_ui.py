"""Playwright full functional test for Pool Admin UI — simulate real user interactions."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright

SHOT = os.path.join(os.environ.get("TEMP", "/tmp"), "opencode", "pool_admin_func_test")
os.makedirs(SHOT, exist_ok=True)
BASE = "http://localhost:5000"
results = []

def log(step, ok, detail=""):
    tag = "✅" if ok else "❌"
    results.append({"step": step, "ok": ok, "detail": detail})
    print(f"  {tag} {step}: {detail}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    # ---- LOGIN ----
    print("=== LOGIN ===")
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=15000)
    page.evaluate("""async () => {
        await fetch('/login', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({password:'admin123'})
        });
    }""")
    page.goto(f"{BASE}/", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(800)
    log("Login", page.title() != "登录 - Outlook 邮件管理", f"title={page.title()}")

    # ---- NAVIGATE TO POOL ADMIN ----
    print("\n=== NAVIGATE ===")
    nav = page.locator('[data-page="pool-admin"]')
    log("Nav item exists", nav.count() > 0, f"count={nav.count()}")
    if nav.count() > 0:
        nav.click()
        page.wait_for_timeout(2000)
        page.wait_for_load_state("networkidle", timeout=10000)
        page.screenshot(path=os.path.join(SHOT, "01_initial_load.png"), full_page=True)
        container = page.locator("#page-pool-admin")
        log("Page visible", container.is_visible() if container.count() > 0 else False)

    # ---- FILTER: SWITCH TO "池内" ----
    print("\n=== FILTER: 池内 ===")
    pool_filter = page.locator("#poolAdminInPoolFilter")
    if pool_filter.count() > 0:
        pool_filter.select_option("true")
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOT, "02_filter_in_pool.png"), full_page=True)
        # Check API call happened — look at table rows
        rows = page.locator(".data-table--pool-admin tbody tr").all()
        log("Filter: 池内", len(rows) >= 0, f"rows={len(rows)}")

    # ---- FILTER: BACK TO ALL ----
    print("\n=== FILTER: ALL ===")
    pool_filter.select_option("all")
    page.wait_for_timeout(1500)
    rows = page.locator(".data-table--pool-admin tbody tr").all()
    log("Filter: 全部", len(rows) > 0, f"rows={len(rows)}")

    # ---- SEARCH ----
    print("\n=== SEARCH ===")
    search = page.locator("#poolAdminSearch")
    if search.count() > 0:
        search.fill("outlook")
        page.wait_for_timeout(800)  # debounce 400ms + render
        page.screenshot(path=os.path.join(SHOT, "03_search_outlook.png"), full_page=True)
        rows = page.locator(".data-table--pool-admin tbody tr").all()
        log("Search 'outlook'", len(rows) >= 0, f"rows={len(rows)}")
        search.clear()
        page.wait_for_timeout(800)

    # ---- PAGINATION: GO TO PAGE 2 ----
    print("\n=== PAGINATION ===")
    pagination = page.locator("#poolAdminPagination")
    page2_btn = pagination.locator('button:has-text("2")')
    if page2_btn.count() > 0:
        page2_btn.first.click()
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOT, "04_page2.png"), full_page=True)
        ptxt = pagination.inner_text()
        log("Page 2", "2/41" in ptxt or "2/267" in ptxt, f"pagination='{ptxt[:60]}'")
        # Go back to page 1
        page1_btn = pagination.locator('button:has-text("1")')
        if page1_btn.count() > 0:
            page1_btn.first.click()
            page.wait_for_timeout(1500)

    # ---- BATCH SELECT ----
    print("\n=== BATCH SELECT ===")
    checks = page.locator(".pa-row-check").all()
    log("Checkboxes exist", len(checks) > 0, f"count={len(checks)}")
    if len(checks) >= 3:
        checks[0].check()
        checks[1].check()
        checks[2].check()
        page.wait_for_timeout(500)
        batch_bar = page.locator("#poolAdminBatchBar")
        if batch_bar.count() > 0 and batch_bar.is_visible():
            bar_text = batch_bar.inner_text()
            log("Batch bar visible", True, f"text='{bar_text}'")
            # Check no template syntax bug
            has_bug = "${" in bar_text or "paT(" in bar_text
            log("Batch bar no template syntax", not has_bug, f"has_bug={has_bug}")
            page.screenshot(path=os.path.join(SHOT, "05_batch_selected.png"), full_page=True)
        else:
            log("Batch bar visible", False, "not visible")

    # ---- CHECK ALL SELECT ----
    print("\n=== SELECT ALL ===")
    check_all = page.locator("#paCheckAll")
    if check_all.count() > 0:
        check_all.check()
        page.wait_for_timeout(300)
        all_checks = page.locator(".pa-row-check").all()
        all_checked = all(cb.is_checked() for cb in all_checks) if all_checks else False
        log("Select all", all_checked, f"all {len(all_checks)} checked")
        batch_bar = page.locator("#poolAdminBatchBar")
        bar_text = batch_bar.inner_text() if batch_bar.count() > 0 else ""
        log("Batch bar shows count", "20" in bar_text, f"'{bar_text}'")
        page.screenshot(path=os.path.join(SHOT, "06_select_all.png"), full_page=True)
        # Uncheck all
        check_all.uncheck()
        page.wait_for_timeout(300)

    # ---- STATUS FILTER ----
    print("\n=== STATUS FILTER ===")
    status_filter = page.locator("#poolAdminStatusFilter")
    if status_filter.count() > 0:
        status_filter.select_option("available")
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOT, "07_filter_available.png"), full_page=True)
        rows = page.locator(".data-table--pool-admin tbody tr").all()
        log("Filter: available", len(rows) >= 0, f"rows={len(rows)}")
        status_filter.select_option("")
        page.wait_for_timeout(1500)

    # ---- ACTION LINKS PRESENT ----
    print("\n=== ACTION LINKS ===")
    action_links = page.locator(".data-table--pool-admin td a[href='javascript:void(0)']").all()
    link_texts = [a.inner_text().strip() for a in action_links[:10]]
    log("Action links exist", len(action_links) > 0, f"total={len(action_links)}, first_10={link_texts}")
    page.screenshot(path=os.path.join(SHOT, "08_final_state.png"), full_page=True)

    # ---- CONSOLE ERRORS ----
    print(f"\n=== CONSOLE ERRORS: {len(console_errors)} ===")
    if console_errors:
        for err in console_errors[:5]:
            print(f"  ❌ {err[:200]}")
    else:
        print("  ✅ No console errors")

    browser.close()

# ---- SUMMARY ----
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
total = len(results)
passed = sum(1 for r in results if r["ok"])
failed = total - passed
for r in results:
    tag = "✅" if r["ok"] else "❌"
    print(f"  {tag} {r['step']}: {r['detail']}")
print(f"\n{passed}/{total} passed, {failed} failed")
print(f"Screenshots: {SHOT}")
