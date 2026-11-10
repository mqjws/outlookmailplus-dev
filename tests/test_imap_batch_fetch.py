"""
E 层：IMAP 批量 FETCH 测试

验证 imap.py 的批量 FETCH 优化：多封邮件一次网络往返。
对应 TDD 矩阵 B-01 ~ B-05。

注意：批量 FETCH 尚未实现，本测试先行编写（TDD 红灯阶段）。
实现时需修改 get_emails_imap_with_server() 中的逐封 FETCH 循环。
"""

import unittest
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch


def _build_rfc822_bytes(subject: str = "Test", body: str = "Hello", sender: str = "a@b.com"):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["Date"] = "Mon, 11 Apr 2026 10:00:00 +0800"
    return msg.as_bytes()


_MOCK_TOKEN_OK = {"success": True, "access_token": "mock-at"}


class TestImapBatchFetch(unittest.TestCase):
    """IMAP 批量 FETCH 测试"""

    def _make_imap_conn(self, mock_cls, search_ids, fetch_response=None):
        conn = MagicMock()
        mock_cls.return_value = conn
        conn.authenticate.return_value = ("OK", [b"Success"])
        conn.select.return_value = ("OK", [b"10"])

        if not search_ids:
            conn.search.return_value = ("OK", [b""])
        else:
            conn.search.return_value = ("OK", [b" ".join(search_ids)])

        if fetch_response is not None:
            conn.fetch.return_value = fetch_response
        return conn

    # B-01: 单封 → 正确解析，等价于逐封 FETCH
    @patch("outlook_web.services.imap.imaplib.IMAP4_SSL")
    @patch("outlook_web.services.imap.get_access_token_imap_result")
    def test_single_email_batch_fetch(self, mock_token, mock_imap_cls):
        from outlook_web.services.imap import get_emails_imap_with_server

        mock_token.return_value = _MOCK_TOKEN_OK
        raw = _build_rfc822_bytes("单封测试", "Hello single")
        conn = self._make_imap_conn(
            mock_imap_cls,
            search_ids=[b"1"],
            fetch_response=("OK", [((b"1 (RFC822)", raw), b")")]),
        )

        result = get_emails_imap_with_server("user@test.com", "cid", "rt", folder="inbox", skip=0, top=1)

        self.assertTrue(result.get("success"))
        emails = result.get("emails", [])
        self.assertEqual(len(emails), 1)
        self.assertIn("单封测试", emails[0].get("subject", ""))

    # B-02: 多封 → 一次 FETCH 返回多封，全部正确解析
    @patch("outlook_web.services.imap.imaplib.IMAP4_SSL")
    @patch("outlook_web.services.imap.get_access_token_imap_result")
    def test_multi_email_batch_fetch(self, mock_token, mock_imap_cls):
        from outlook_web.services.imap import get_emails_imap_with_server

        mock_token.return_value = _MOCK_TOKEN_OK

        # 构造 5 封邮件
        fetch_data = []
        for i in range(5):
            raw = _build_rfc822_bytes(f"邮件 {i+1}", f"Body {i+1}", f"s{i+1}@test.com")
            fetch_data.append(((f"{i+1} (RFC822)".encode(), raw), b")"))

        flat_data = [item for pair in fetch_data for item in pair]
        conn = self._make_imap_conn(
            mock_imap_cls,
            search_ids=[str(i + 1).encode() for i in range(5)],
            fetch_response=("OK", flat_data),
        )

        result = get_emails_imap_with_server("user@test.com", "cid", "rt", folder="inbox", skip=0, top=5)

        self.assertTrue(result.get("success"))
        emails = result.get("emails", [])
        self.assertEqual(len(emails), 5)
        # fetch 只调用一次（批量）
        self.assertEqual(conn.fetch.call_count, 1)

    # B-03: SEARCH 返回 0 个 ID → 不发起 FETCH
    @patch("outlook_web.services.imap.imaplib.IMAP4_SSL")
    @patch("outlook_web.services.imap.get_access_token_imap_result")
    def test_empty_search_no_fetch(self, mock_token, mock_imap_cls):
        from outlook_web.services.imap import get_emails_imap_with_server

        mock_token.return_value = _MOCK_TOKEN_OK
        conn = self._make_imap_conn(mock_imap_cls, search_ids=[])

        result = get_emails_imap_with_server("user@test.com", "cid", "rt", folder="inbox", skip=0, top=5)

        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("emails"), [])
        conn.fetch.assert_not_called()

    # B-04: 部分解析失败 → 其余邮件正常返回
    @patch("outlook_web.services.imap.imaplib.IMAP4_SSL")
    @patch("outlook_web.services.imap.get_access_token_imap_result")
    def test_partial_parse_failure_returns_valid_emails(self, mock_token, mock_imap_cls):
        from outlook_web.services.imap import get_emails_imap_with_server

        mock_token.return_value = _MOCK_TOKEN_OK

        good_raw = _build_rfc822_bytes("Good Email", "Good body")
        # 损坏的 RFC822
        bad_raw = b"This is not a valid email"

        fetch_data = [
            ((b"1 (RFC822)", good_raw), b")"),
            ((b"2 (RFC822)", bad_raw), b")"),
            ((b"3 (RFC822)", good_raw), b")"),
        ]
        flat_data = [item for pair in fetch_data for item in pair]

        conn = self._make_imap_conn(
            mock_imap_cls,
            search_ids=[b"1", b"2", b"3"],
            fetch_response=("OK", flat_data),
        )

        result = get_emails_imap_with_server("user@test.com", "cid", "rt", folder="inbox", skip=0, top=3)

        self.assertTrue(result.get("success"))
        emails = result.get("emails", [])
        # 至少有 2 封成功解析（损坏的那封可能跳过或包含部分信息）
        self.assertGreaterEqual(len(emails), 2)

    # B-05: 大批量 top=20
    @patch("outlook_web.services.imap.imaplib.IMAP4_SSL")
    @patch("outlook_web.services.imap.get_access_token_imap_result")
    def test_large_batch_fetch(self, mock_token, mock_imap_cls):
        from outlook_web.services.imap import get_emails_imap_with_server

        mock_token.return_value = _MOCK_TOKEN_OK

        fetch_data = []
        ids = []
        for i in range(20):
            raw = _build_rfc822_bytes(f"Email {i+1}", f"Body {i+1}")
            fetch_data.append(((f"{i+1} (RFC822)".encode(), raw), b")"))
            ids.append(str(i + 1).encode())

        flat_data = [item for pair in fetch_data for item in pair]
        conn = self._make_imap_conn(
            mock_imap_cls,
            search_ids=ids,
            fetch_response=("OK", flat_data),
        )

        result = get_emails_imap_with_server("user@test.com", "cid", "rt", folder="inbox", skip=0, top=20)

        self.assertTrue(result.get("success"))
        emails = result.get("emails", [])
        self.assertEqual(len(emails), 20)


if __name__ == "__main__":
    unittest.main()
