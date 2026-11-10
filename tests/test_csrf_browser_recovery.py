import re
import threading
import unittest
import uuid

from tests._import_app import clear_login_attempts, import_web_app_module

try:
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server

    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False


_UNSAFE_BROWSER_PORTS = {
    1,
    7,
    9,
    11,
    13,
    15,
    17,
    19,
    20,
    21,
    22,
    23,
    25,
    37,
    42,
    43,
    53,
    77,
    79,
    87,
    95,
    101,
    102,
    103,
    104,
    109,
    110,
    111,
    113,
    115,
    117,
    119,
    123,
    135,
    137,
    139,
    143,
    161,
    179,
    389,
    427,
    465,
    512,
    513,
    514,
    515,
    526,
    530,
    531,
    532,
    540,
    548,
    554,
    556,
    563,
    587,
    601,
    636,
    989,
    990,
    993,
    995,
    1719,
    1720,
    1723,
    2049,
    3659,
    4045,
    5060,
    5061,
    6000,
    6566,
    6665,
    6666,
    6667,
    6668,
    6669,
    6697,
    10080,
}


class _LiveServerThread(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self._server = None
        self.port = None
        for _ in range(20):
            server = make_server("127.0.0.1", 0, app)
            port = int(server.server_port)
            if port not in _UNSAFE_BROWSER_PORTS:
                self._server = server
                self.port = port
                break
            server.server_close()
        if self._server is None or self.port is None:
            raise RuntimeError("failed to allocate a browser-safe test port")

    def run(self):
        self._server.serve_forever()

    def shutdown(self):
        self._server.shutdown()


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "playwright or werkzeug is unavailable")
class CsrfBrowserRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app
        cls._original_csrf_enabled = cls.app.config.get("WTF_CSRF_ENABLED")
        cls._original_csrf_check_default = cls.app.config.get("WTF_CSRF_CHECK_DEFAULT")
        cls._server = None
        cls._playwright = None
        cls._browser = None

        # 先检查 Playwright 是否真正可用（二进制存在），再修改全局 CSRF 配置
        try:
            _pw = sync_playwright().start()
        except Exception as exc:
            raise unittest.SkipTest(f"playwright is unavailable: {exc}")

        # Playwright 可用，现在才开启 CSRF（确保 tearDownClass 能被调用来还原）
        cls.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=True,
            WTF_CSRF_CHECK_DEFAULT=True,
        )

        cls._server = _LiveServerThread(cls.app)
        cls._server.start()
        cls.base_url = f"http://127.0.0.1:{cls._server.port}"
        cls._playwright = _pw
        try:
            cls._browser = _pw.chromium.launch(headless=True)
        except Exception as exc:
            _pw.stop()
            cls._server.shutdown()
            cls._server.join(timeout=5)
            cls.app.config.update(
                WTF_CSRF_ENABLED=cls._original_csrf_enabled,
                WTF_CSRF_CHECK_DEFAULT=cls._original_csrf_check_default,
            )
            raise unittest.SkipTest(f"playwright chromium is unavailable: {exc}")

    @classmethod
    def tearDownClass(cls):
        try:
            cls._browser.close()
        finally:
            try:
                cls._playwright.stop()
            finally:
                cls._server.shutdown()
                cls._server.join(timeout=5)
                cls.app.config.update(
                    WTF_CSRF_ENABLED=cls._original_csrf_enabled,
                    WTF_CSRF_CHECK_DEFAULT=cls._original_csrf_check_default,
                )

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db

            db = get_db()
            db.execute("DELETE FROM accounts WHERE email LIKE '%@csrf-browser.test'")
            db.commit()

    def _account_exists(self, email_addr: str) -> bool:
        conn = self.module.create_sqlite_connection()
        try:
            row = conn.execute("SELECT 1 FROM accounts WHERE email = ? LIMIT 1", (email_addr,)).fetchone()
            return row is not None
        finally:
            conn.close()

    def test_browser_recovers_after_stale_csrf_token_and_retries_once(self):
        unique = uuid.uuid4().hex[:10]
        email_addr = f"browser_{unique}@csrf-browser.test"
        account_line = f"{email_addr}----pwd----cid_{unique}----rt_{unique}"

        context = self._browser.new_context(locale="zh-CN")
        page = context.new_page()
        account_post_statuses = []
        csrf_token_request_count = 0

        def _collect_account_import_response(response):
            nonlocal csrf_token_request_count
            request = response.request
            if request.method == "POST" and response.url.endswith("/api/accounts"):
                account_post_statuses.append(response.status)
            if request.method == "GET" and response.url.endswith("/api/csrf-token"):
                csrf_token_request_count += 1

        page.on("response", _collect_account_import_response)

        try:
            page.goto(f"{self.base_url}/login")
            page.fill("#password", "testpass123")
            page.click("#loginBtn")
            # 该用例的关注点是「CSRF 过期后自动重试一次」；
            # 登录跳转本身在 CI/全量用例并发资源竞争时可能略慢，默认 30s 偶发超时会导致用例抖动。
            # 因此这里显式放宽等待时间，并改为等待可交互 DOM，而不是等待所有后台请求彻底静默。
            page.wait_for_url(re.compile(r".*/$"), timeout=60_000)
            page.locator("#app").wait_for(timeout=15_000)
            page.locator('.nav-item[data-page="mailbox"]').click()
            page.wait_for_function(
                """() => {
                    const mailboxPage = document.getElementById('page-mailbox');
                    return mailboxPage && !mailboxPage.classList.contains('page-hidden');
                }""",
                timeout=15_000,
            )
            page.wait_for_function("""() => {
                    const select = document.getElementById('importGroupSelect');
                    return select && select.options.length > 0;
                }""")
            account_post_statuses.clear()
            csrf_token_request_count = 0

            page.evaluate(
                """(line) => {
                    showAddAccountModal();
                    document.getElementById('accountInput').value = line;
                    const select = document.getElementById('importGroupSelect');
                    if (select && select.options.length > 0) {
                        select.value = select.options[0].value;
                    }
                    csrfToken = 'stale-csrf-token';
                    addAccount();
                }""",
                account_line,
            )

            page.locator("#toast-container .toast.success").filter(has_text="导入完成").wait_for(timeout=15000)
            page.wait_for_function(
                """(targetEmail) => {
                    const cards = Array.from(document.querySelectorAll('.account-card .account-email'));
                    return cards.some((node) => (node.textContent || '').includes(targetEmail));
                }""",
                arg=email_addr,
                timeout=15000,
            )

            self.assertEqual(account_post_statuses, [400, 200])
            self.assertEqual(csrf_token_request_count, 1)
            self.assertTrue(self._account_exists(email_addr))
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()
