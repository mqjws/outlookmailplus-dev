"""
F 层：IMAP 并发双服务器测试

验证 imap.py 新增的 get_emails_imap_concurrent() 竞速逻辑。
对应 TDD 矩阵 P-01 ~ P-06。

注意：并发函数尚未实现，本测试先行编写（TDD 红灯阶段）。
"""

import time
import unittest
from concurrent.futures import Future
from email.mime.text import MIMEText
from unittest.mock import MagicMock, call, patch


def _build_rfc822_bytes(subject="Test", body="Hello"):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = "test@example.com"
    msg["Date"] = "Mon, 11 Apr 2026 10:00:00 +0800"
    return msg.as_bytes()


def _make_success_result(emails_count=1, server_label="server1"):
    """构造成功的 IMAP fetch 结果"""
    emails = []
    for i in range(emails_count):
        emails.append(
            {
                "id": str(i + 1),
                "subject": f"Email {i+1} from {server_label}",
                "from": "test@example.com",
                "date": "Mon, 11 Apr 2026 10:00:00 +0800",
                "body_preview": f"Preview {i+1}",
            }
        )
    return {"success": True, "emails": emails}


def _make_error_result():
    """构造失败的 IMAP fetch 结果"""
    return {
        "success": False,
        "error": {"code": "EMAIL_FETCH_FAILED", "message": "认证失败"},
    }


class TestImapConcurrentServers(unittest.TestCase):
    """IMAP 并发双服务器测试"""

    # P-01: 两台都成功 → 返回先到的结果
    @patch("outlook_web.services.imap.get_emails_imap_with_server")
    def test_first_success_wins(self, mock_fetch):
        from outlook_web.services.imap import get_emails_imap_concurrent

        def side_effect(*args, **kwargs):
            server = kwargs.get("server", args[6] if len(args) > 6 else "")
            if server == "outlook.live.com":
                time.sleep(0.05)
                return _make_success_result(1, "live")
            else:
                time.sleep(0.2)
                return _make_success_result(1, "office365")

        mock_fetch.side_effect = side_effect

        result = get_emails_imap_concurrent(
            "user@test.com",
            "cid",
            "rt",
            "inbox",
            0,
            1,
            servers=("outlook.live.com", "outlook.office365.com"),
        )

        self.assertTrue(result.get("success"))
        # 应返回较快的 live 服务器结果
        self.assertIn("live", result["emails"][0]["subject"])

    # P-02: 一台失败一台成功 → 返回成功的那台
    @patch("outlook_web.services.imap.get_emails_imap_with_server")
    def test_one_fail_one_success_returns_success(self, mock_fetch):
        from outlook_web.services.imap import get_emails_imap_concurrent

        def side_effect(*args, **kwargs):
            server = kwargs.get("server", args[6] if len(args) > 6 else "")
            if server == "outlook.live.com":
                return _make_error_result()
            return _make_success_result(1, "office365")

        mock_fetch.side_effect = side_effect

        result = get_emails_imap_concurrent(
            "user@test.com",
            "cid",
            "rt",
            "inbox",
            0,
            1,
            servers=("outlook.live.com", "outlook.office365.com"),
        )

        self.assertTrue(result.get("success"))

    # P-03: 两台都失败 → 返回错误
    @patch("outlook_web.services.imap.get_emails_imap_with_server")
    def test_both_fail_returns_error(self, mock_fetch):
        from outlook_web.services.imap import get_emails_imap_concurrent

        mock_fetch.return_value = _make_error_result()

        result = get_emails_imap_concurrent(
            "user@test.com",
            "cid",
            "rt",
            "inbox",
            0,
            1,
            servers=("outlook.live.com", "outlook.office365.com"),
        )

        self.assertFalse(result.get("success"))

    # P-04: 一台超时一台成功 → 返回成功的
    @patch("outlook_web.services.imap.get_emails_imap_with_server")
    def test_timeout_fallback(self, mock_fetch):
        from outlook_web.services.imap import get_emails_imap_concurrent

        def side_effect(*args, **kwargs):
            server = kwargs.get("server", args[6] if len(args) > 6 else "")
            if server == "outlook.live.com":
                time.sleep(5)  # 模拟超时
                return _make_error_result()
            return _make_success_result(1, "office365")

        mock_fetch.side_effect = side_effect

        result = get_emails_imap_concurrent(
            "user@test.com",
            "cid",
            "rt",
            "inbox",
            0,
            1,
            servers=("outlook.live.com", "outlook.office365.com"),
        )

        self.assertTrue(result.get("success"))

    # P-05: 只传单台服务器 → 不并发
    @patch("outlook_web.services.imap.get_emails_imap_with_server")
    def test_single_server_no_concurrency(self, mock_fetch):
        from outlook_web.services.imap import get_emails_imap_concurrent

        mock_fetch.return_value = _make_success_result(1, "live")

        result = get_emails_imap_concurrent(
            "user@test.com",
            "cid",
            "rt",
            "inbox",
            0,
            1,
            servers=("outlook.live.com",),
        )

        self.assertTrue(result.get("success"))
        # 只调用一次（不并发）
        self.assertEqual(mock_fetch.call_count, 1)

    # P-06: 并发结束后两个调用都完成（不检查 logout，交由 get_emails_imap_with_server 内部处理）
    @patch("outlook_web.services.imap.get_emails_imap_with_server")
    def test_both_servers_called(self, mock_fetch):
        from outlook_web.services.imap import get_emails_imap_concurrent

        mock_fetch.return_value = _make_success_result(1, "any")

        get_emails_imap_concurrent(
            "user@test.com",
            "cid",
            "rt",
            "inbox",
            0,
            1,
            servers=("outlook.live.com", "outlook.office365.com"),
        )

        # 两台服务器都应被调用
        self.assertEqual(mock_fetch.call_count, 2)


if __name__ == "__main__":
    unittest.main()
