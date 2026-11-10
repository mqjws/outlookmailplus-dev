import unittest
from unittest.mock import MagicMock, patch

import requests

from outlook_web.services import gptmail


class TestGPTMailErrorHandling(unittest.TestCase):
    """测试 legacy 临时邮箱 bridge 的错误处理"""

    def test_gptmail_request_no_api_key(self):
        """测试 API Key 未配置的情况"""
        with patch("outlook_web.services.gptmail.get_gptmail_api_key", return_value=""):
            result = gptmail.gptmail_request("GET", "/api/test")

            self.assertFalse(result["success"])
            self.assertEqual(result["error_type"], "CONFIG_ERROR")
            self.assertIn("未配置", result["error"])

    def test_gptmail_request_401_unauthorized(self):
        """测试 API Key 无效的情况"""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch(
            "outlook_web.services.gptmail.get_gptmail_api_key",
            return_value="invalid_key",
        ):
            with patch("requests.get", return_value=mock_response):
                result = gptmail.gptmail_request("GET", "/api/test")

                self.assertFalse(result["success"])
                self.assertEqual(result["error_type"], "AUTH_ERROR")
                self.assertIn("无效", result["error"])

    def test_gptmail_request_timeout(self):
        """测试请求超时的情况"""
        with patch("outlook_web.services.gptmail.get_gptmail_api_key", return_value="test_key"):
            with patch("requests.get", side_effect=requests.exceptions.Timeout()):
                result = gptmail.gptmail_request("GET", "/api/test")

                self.assertFalse(result["success"])
                self.assertEqual(result["error_type"], "TIMEOUT_ERROR")
                self.assertIn("超时", result["error"])

    def test_gptmail_request_connection_error(self):
        """测试网络连接失败的情况"""
        with patch("outlook_web.services.gptmail.get_gptmail_api_key", return_value="test_key"):
            with patch(
                "requests.get",
                side_effect=requests.exceptions.ConnectionError("Connection refused"),
            ):
                result = gptmail.gptmail_request("GET", "/api/test")

                self.assertFalse(result["success"])
                self.assertEqual(result["error_type"], "CONNECTION_ERROR")
                self.assertIn("连接", result["error"])

    def test_gptmail_request_500_server_error(self):
        """测试服务器错误的情况"""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("outlook_web.services.gptmail.get_gptmail_api_key", return_value="test_key"):
            with patch("requests.get", return_value=mock_response):
                result = gptmail.gptmail_request("GET", "/api/test")

                self.assertFalse(result["success"])
                self.assertEqual(result["error_type"], "SERVER_ERROR")
                self.assertIn("不可用", result["error"])

    def test_gptmail_request_429_rate_limit(self):
        """测试请求频率超限的情况"""
        mock_response = MagicMock()
        mock_response.status_code = 429

        with patch("outlook_web.services.gptmail.get_gptmail_api_key", return_value="test_key"):
            with patch("requests.get", return_value=mock_response):
                result = gptmail.gptmail_request("GET", "/api/test")

                self.assertFalse(result["success"])
                self.assertEqual(result["error_type"], "RATE_LIMIT_ERROR")
                self.assertIn("频率超限", result["error"])

    def test_generate_temp_email_success(self):
        """测试成功生成临时邮箱"""
        mock_result = {"success": True, "data": {"email": "test@example.com"}}

        with patch("outlook_web.services.gptmail.gptmail_request", return_value=mock_result):
            email, error = gptmail.generate_temp_email()

            self.assertEqual(email, "test@example.com")
            self.assertIsNone(error)

    def test_generate_temp_email_api_key_not_configured(self):
        """测试 API Key 未配置时生成临时邮箱"""
        mock_result = {
            "success": False,
            "error": "临时邮箱 API Key 未配置",
            "error_type": "CONFIG_ERROR",
            "details": "请在系统设置中配置临时邮箱 API Key",
        }

        with patch("outlook_web.services.gptmail.gptmail_request", return_value=mock_result):
            email, error = gptmail.generate_temp_email()

            self.assertIsNone(email)
            self.assertIn("未配置", error)
            self.assertIn("系统设置", error)

    def test_generate_temp_email_timeout(self):
        """测试请求超时时生成临时邮箱"""
        mock_result = {
            "success": False,
            "error": "API 请求超时",
            "error_type": "TIMEOUT_ERROR",
            "details": "请求超过 30 秒未响应，请检查网络连接或稍后重试",
        }

        with patch("outlook_web.services.gptmail.gptmail_request", return_value=mock_result):
            email, error = gptmail.generate_temp_email()

            self.assertIsNone(email)
            self.assertIn("超时", error)
            self.assertIn("30 秒", error)

    def test_generate_temp_email_missing_email_field(self):
        """测试 API 返回数据缺少 email 字段"""
        mock_result = {"success": True, "data": {}}  # 缺少 email 字段

        with patch("outlook_web.services.gptmail.gptmail_request", return_value=mock_result):
            email, error = gptmail.generate_temp_email()

            self.assertIsNone(email)
            self.assertIn("格式错误", error)
            self.assertIn("email", error)

    def test_generate_temp_email_with_prefix_and_domain(self):
        """测试使用 prefix 和 domain 生成临时邮箱"""
        mock_result = {"success": True, "data": {"email": "custom@example.com"}}

        with patch("outlook_web.services.gptmail.gptmail_request", return_value=mock_result) as mock_request:
            email, error = gptmail.generate_temp_email(prefix="custom", domain="example.com")

            self.assertEqual(email, "custom@example.com")
            self.assertIsNone(error)

            # 验证调用参数
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            self.assertEqual(call_args[0][0], "POST")
            self.assertEqual(call_args[1]["json_data"], {"prefix": "custom", "domain": "example.com"})


if __name__ == "__main__":
    unittest.main()
