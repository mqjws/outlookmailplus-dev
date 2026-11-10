from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from tests._import_app import clear_login_attempts, import_web_app_module


class WebhookPushServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("webhook_notification_enabled", "false")
            settings_repo.set_setting("webhook_notification_url", "")
            settings_repo.set_setting("webhook_notification_token", "")

    def _resp(self, status_code: int, text: str = ""):
        resp = Mock()
        resp.status_code = status_code
        resp.text = text
        return resp

    def test_send_webhook_message_success_on_2xx(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            return_value=self._resp(204),
        ) as post_mock:
            webhook_push.send_webhook_message(
                url="https://example.com/hook",
                token="",
                text_body="hello",
                timeout_sec=10,
                retry=1,
            )

        post_mock.assert_called_once()
        kwargs = post_mock.call_args.kwargs
        self.assertEqual(kwargs.get("timeout"), 10)
        self.assertEqual(kwargs.get("headers", {}).get("Content-Type"), "text/plain; charset=utf-8")
        self.assertNotIn("X-Webhook-Token", kwargs.get("headers", {}))

    def test_send_webhook_message_retries_once_then_success(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            side_effect=[self._resp(500, "err"), self._resp(200, "ok")],
        ) as post_mock:
            webhook_push.send_webhook_message(
                url="https://example.com/hook",
                token="",
                text_body="hello",
                timeout_sec=10,
                retry=1,
            )

        self.assertEqual(post_mock.call_count, 2)

    def test_send_webhook_message_retries_once_then_fail(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            side_effect=[self._resp(500, "err"), self._resp(500, "err2")],
        ) as post_mock:
            with self.assertRaises(webhook_push.WebhookPushError) as ctx:
                webhook_push.send_webhook_message(
                    url="https://example.com/hook",
                    token="",
                    text_body="hello",
                    timeout_sec=10,
                    retry=1,
                )

        self.assertEqual(post_mock.call_count, 2)
        self.assertEqual(ctx.exception.code, "WEBHOOK_SEND_FAILED")

    def test_send_webhook_message_timeout_uses_10_seconds(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            side_effect=requests.Timeout("timeout"),
        ) as post_mock:
            with self.assertRaises(webhook_push.WebhookPushError):
                webhook_push.send_webhook_message(
                    url="https://example.com/hook",
                    token="",
                    text_body="hello",
                    timeout_sec=10,
                    retry=0,
                )

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(post_mock.call_args.kwargs.get("timeout"), 10)

    def test_send_webhook_message_without_token_omits_header(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            return_value=self._resp(200),
        ) as post_mock:
            webhook_push.send_webhook_message(
                url="https://example.com/hook",
                token="",
                text_body="hello",
            )

        headers = post_mock.call_args.kwargs.get("headers", {})
        self.assertNotIn("X-Webhook-Token", headers)

    def test_send_webhook_message_with_token_sets_header(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            return_value=self._resp(200),
        ) as post_mock:
            webhook_push.send_webhook_message(
                url="https://example.com/hook",
                token="token-123",
                text_body="hello",
            )

        headers = post_mock.call_args.kwargs.get("headers", {})
        self.assertEqual(headers.get("X-Webhook-Token"), "token-123")

    def test_build_business_webhook_text_contains_minimum_fields(self):
        from outlook_web.services import webhook_push

        source = {
            "source_type": "account",
            "label": "sender@example.com",
        }
        message = {
            "folder": "inbox",
            "sender": "from@example.com",
            "subject": "hello",
            "received_at": "2026-04-14T12:00:00",
            "preview": "body preview",
        }

        text = webhook_push.build_business_webhook_text(source, message)
        self.assertIn("来源邮箱:", text)
        self.assertIn("来源类型:", text)
        self.assertIn("文件夹:", text)
        self.assertIn("发件人:", text)
        self.assertIn("主题:", text)
        self.assertIn("时间:", text)
        self.assertIn("正文摘要:", text)


if __name__ == "__main__":
    unittest.main()
