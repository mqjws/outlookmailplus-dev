from __future__ import annotations

import unittest
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class TempMailProviderContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("temp_mail_provider", "custom_domain_temp_mail")
            settings_repo.set_setting(
                "temp_mail_domains",
                '[{"name":"provider-contract.test","enabled":true}]',
            )
            settings_repo.set_setting("temp_mail_default_domain", "provider-contract.test")
            settings_repo.set_setting(
                "temp_mail_prefix_rules",
                '{"min_length":1,"max_length":16,"pattern":"^[a-z0-9-]+$"}',
            )

    def test_get_options_exposes_runtime_provider_and_formal_label(self):
        with self.app.app_context():
            from outlook_web.services.temp_mail_provider_custom import CustomTempMailProvider

            provider = CustomTempMailProvider()
            options = provider.get_options()

        self.assertEqual(options["provider"], "custom_domain_temp_mail")
        self.assertEqual(options["provider_name"], "custom_domain_temp_mail")
        self.assertEqual(options["provider_label"], "temp_mail")
        self.assertEqual(options["domains"][0]["name"], "provider-contract.test")

    def test_create_mailbox_returns_internal_meta_contract(self):
        with self.app.app_context():
            from outlook_web.services.temp_mail_provider_custom import CustomTempMailProvider

            provider = CustomTempMailProvider()
            with patch(
                "outlook_web.services.gptmail.generate_temp_email",
                return_value=("demo@provider-contract.test", None),
            ):
                result = provider.create_mailbox(prefix="demo", domain="provider-contract.test")

        self.assertTrue(result["success"])
        self.assertEqual(result["email"], "demo@provider-contract.test")
        self.assertEqual(result["meta"]["provider_name"], "custom_domain_temp_mail")
        self.assertEqual(result["meta"]["provider_debug"]["bridge"], "gptmail")

    def test_mailbox_first_read_methods_accept_descriptor(self):
        mailbox = {"email": "demo@provider-contract.test"}
        with self.app.app_context():
            from outlook_web.services.temp_mail_provider_custom import CustomTempMailProvider

            provider = CustomTempMailProvider()
            with patch("outlook_web.services.gptmail.get_temp_emails_from_api", return_value=[]) as list_mock:
                provider.list_messages(mailbox)
            with patch(
                "outlook_web.services.gptmail.get_temp_email_detail_from_api",
                return_value={"id": "msg-1"},
            ) as detail_mock:
                provider.get_message_detail(mailbox, "msg-1")
            with patch("outlook_web.services.gptmail.delete_temp_email_from_api", return_value=True) as delete_mock:
                provider.delete_message(mailbox, "msg-1")
            with patch("outlook_web.services.gptmail.clear_temp_emails_from_api", return_value=True) as clear_mock:
                provider.clear_messages(mailbox)

        list_mock.assert_called_once_with("demo@provider-contract.test")
        detail_mock.assert_called_once_with("demo@provider-contract.test", "msg-1")
        delete_mock.assert_called_once_with("demo@provider-contract.test", "msg-1")
        clear_mock.assert_called_once_with("demo@provider-contract.test")
