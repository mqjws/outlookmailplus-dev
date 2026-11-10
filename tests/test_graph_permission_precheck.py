"""
B 层：Graph API 权限预检测试

验证 graph.py 的 scope 解析和无权限跳过逻辑。
对应 TDD 矩阵 G-01 ~ G-06。

注意：权限预检功能尚未实现，本测试先行编写（TDD 红灯阶段）。
实现时需在 graph.py 新增 has_mail_read_permission() 并修改 get_access_token_graph_result 返回 scope。
"""

import unittest
from unittest.mock import MagicMock, patch


def _make_graph_token_response(access_token: str, scope: str = "", refresh_token: str = None):
    """构造 MS Graph token endpoint 的 mock Response"""
    resp = MagicMock()
    resp.status_code = 200
    body = {
        "access_token": access_token,
        "scope": scope,
        "token_type": "Bearer",
        "expires_in": 3599,
    }
    if refresh_token:
        body["refresh_token"] = refresh_token
    resp.json.return_value = body
    return resp


def _make_error_response(status: int = 400, error_description: str = "invalid_grant"):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = {"error": "invalid_grant", "error_description": error_description}
    resp.text = '{"error":"invalid_grant"}'
    resp.headers = {}
    return resp


class TestGraphPermissionPrecheck(unittest.TestCase):
    """Graph API 权限预检测试"""

    # ------------------------------------------------------------------
    # has_mail_read_permission 工具函数测试
    # ------------------------------------------------------------------

    def test_has_mail_read_permission_true(self):
        """G-01: scope 含 Mail.Read → True"""
        from outlook_web.services.graph import has_mail_read_permission

        self.assertTrue(has_mail_read_permission("User.Read Mail.Read profile"))

    def test_has_mail_readwrite_permission_true(self):
        """G-02: scope 含 Mail.ReadWrite → True"""
        from outlook_web.services.graph import has_mail_read_permission

        self.assertTrue(has_mail_read_permission("Mail.ReadWrite User.Read"))

    def test_no_mail_permission_returns_false(self):
        """G-03: scope 无邮件权限 → False"""
        from outlook_web.services.graph import has_mail_read_permission

        self.assertFalse(has_mail_read_permission("User.Read profile openid email"))

    def test_empty_scope_returns_false(self):
        """G-04: scope 为空 → False"""
        from outlook_web.services.graph import has_mail_read_permission

        self.assertFalse(has_mail_read_permission(""))
        self.assertFalse(has_mail_read_permission(None))

    def test_scope_case_sensitive(self):
        """G-06: MS scope 区分大小写"""
        from outlook_web.services.graph import has_mail_read_permission

        self.assertFalse(has_mail_read_permission("mail.read user.read"))
        self.assertFalse(has_mail_read_permission("MAIL.READ"))

    # ------------------------------------------------------------------
    # get_access_token_graph_result 返回 scope 字段
    # ------------------------------------------------------------------

    @patch("outlook_web.services.graph.requests.post")
    def test_token_result_includes_scope(self, mock_post):
        """token 结果应包含 scope 字段"""
        from outlook_web.services.graph import get_access_token_graph_result

        mock_post.return_value = _make_graph_token_response("at-123", scope="User.Read Mail.Read profile")

        result = get_access_token_graph_result("cid", "rt", proxy_url=None)
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("scope"), "User.Read Mail.Read profile")

    @patch("outlook_web.services.graph.requests.post")
    def test_token_refresh_failure_returns_auth_expired(self, mock_post):
        """G-05: token 刷新失败 → 正常返回错误，不检查 scope"""
        from outlook_web.services.graph import get_access_token_graph_result

        mock_post.return_value = _make_error_response(400)

        result = get_access_token_graph_result("cid", "rt", proxy_url=None)
        self.assertFalse(result.get("success"))
        self.assertIsNone(result.get("scope"))

    @patch("outlook_web.services.graph.requests.post")
    def test_refresh_token_falls_back_to_imap_scope_on_aadsts90023(self, mock_post):
        """Graph .default 无适用权限时，应降级用 IMAP scope 刷新并返回新 refresh_token。"""
        from outlook_web.services.graph import (
            DEFAULT_GRAPH_SCOPE,
            IMAP_REFRESH_SCOPE,
            test_refresh_token_with_rotation,
        )

        mock_post.side_effect = [
            _make_error_response(
                400,
                "AADSTS90023: No applicable permissions were found for this user.",
            ),
            _make_graph_token_response(
                "imap-access-token",
                scope="https://outlook.office.com/IMAP.AccessAsUser.All",
                refresh_token="rt-rotated-imap",
            ),
        ]

        ok, error_msg, new_refresh_token = test_refresh_token_with_rotation("cid", "rt")

        self.assertTrue(ok)
        self.assertIsNone(error_msg)
        self.assertEqual(new_refresh_token, "rt-rotated-imap")
        self.assertEqual(mock_post.call_count, 2)
        first_payload = mock_post.call_args_list[0].kwargs["data"]
        second_payload = mock_post.call_args_list[1].kwargs["data"]
        self.assertEqual(first_payload["scope"], DEFAULT_GRAPH_SCOPE)
        self.assertEqual(second_payload["scope"], IMAP_REFRESH_SCOPE)

    # ------------------------------------------------------------------
    # get_emails_graph 跳过无权限调用
    # ------------------------------------------------------------------

    @patch("outlook_web.services.graph.requests.get")
    @patch("outlook_web.services.graph.requests.post")
    def test_get_emails_graph_skips_api_when_no_permission(self, mock_post, mock_get):
        """无 Mail.Read 权限时不发起 Graph messages API 请求"""
        from outlook_web.services.graph import get_emails_graph

        mock_post.return_value = _make_graph_token_response("at-123", scope="User.Read profile openid email")

        result = get_emails_graph("cid", "rt", folder="inbox", skip=0, top=1)

        self.assertFalse(result.get("success"))
        self.assertTrue(result.get("no_mail_permission"))
        # Graph messages API 不应被调用
        mock_get.assert_not_called()

    @patch("outlook_web.services.graph.requests.get")
    @patch("outlook_web.services.graph.requests.post")
    def test_get_emails_graph_calls_api_when_has_permission(self, mock_post, mock_get):
        """有 Mail.Read 权限时正常调用 Graph API"""
        from outlook_web.services.graph import get_emails_graph

        mock_post.return_value = _make_graph_token_response("at-123", scope="User.Read Mail.Read profile")
        # Graph messages API 返回
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {"value": []}
        mock_get.return_value = mock_get_resp

        result = get_emails_graph("cid", "rt", folder="inbox", skip=0, top=1)

        # Graph messages API 应被调用
        mock_get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
