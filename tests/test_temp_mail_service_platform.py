from __future__ import annotations

import unittest

from tests._import_app import clear_login_attempts, import_web_app_module


class _MailboxFirstProvider:
    def __init__(self):
        self.create_calls = []
        self.list_calls = []
        self.delete_mailbox_calls = []

    def get_options(self):
        return {
            "domains": [{"name": "service-platform.test", "enabled": True, "is_default": True}],
            "prefix_rules": {"min_length": 1, "max_length": 32, "pattern": r"^[a-z0-9][a-z0-9._-]*$"},
            "provider": "custom_domain_temp_mail",
            "provider_name": "custom_domain_temp_mail",
            "provider_label": "temp_mail",
        }

    def create_mailbox(self, *, prefix=None, domain=None):
        email_addr = f"{prefix or 'auto'}@{domain or 'service-platform.test'}"
        self.create_calls.append({"prefix": prefix, "domain": domain, "email": email_addr})
        return {
            "success": True,
            "email": email_addr,
            "meta": {
                "provider_name": "custom_domain_temp_mail",
                "provider_cursor": f"cursor:{email_addr}",
                "provider_capabilities": {
                    "delete_mailbox": False,
                    "delete_message": True,
                    "clear_messages": True,
                },
            },
        }

    def delete_mailbox(self, mailbox):
        self.delete_mailbox_calls.append(mailbox)
        return True

    def list_messages(self, mailbox):
        self.list_calls.append(mailbox)
        return [
            {
                "id": "msg-1",
                "from_address": "noreply@example.com",
                "subject": "Your verification code",
                "content": "Code: 112233",
                "timestamp": 1711111111,
            }
        ]

    def get_message_detail(self, mailbox, message_id):
        return {
            "id": message_id,
            "from_address": "noreply@example.com",
            "subject": "Your verification code",
            "content": "Code: 112233",
            "html_content": "",
            "timestamp": 1711111111,
        }

    def delete_message(self, mailbox, message_id):
        return True

    def clear_messages(self, mailbox):
        return True


class TempMailServicePlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db

            db = get_db()
            db.execute("DELETE FROM temp_email_messages WHERE email_address LIKE '%@service-platform.test'")
            db.execute("DELETE FROM temp_emails WHERE email LIKE '%@service-platform.test'")
            db.commit()

    def test_service_uses_factory_and_persists_provider_meta(self):
        provider = _MailboxFirstProvider()
        with self.app.app_context():
            from outlook_web.repositories import temp_emails as temp_emails_repo
            from outlook_web.services.temp_mail_service import TempMailService

            service = TempMailService(provider_factory=lambda provider_name=None: provider)
            mailbox = service.generate_user_mailbox(prefix="demo", domain="service-platform.test")
            record = temp_emails_repo.get_temp_email_by_address("demo@service-platform.test")

        self.assertEqual(mailbox["email"], "demo@service-platform.test")
        self.assertEqual(provider.create_calls[0]["domain"], "service-platform.test")
        self.assertEqual(record["meta_json"]["provider_cursor"], "cursor:demo@service-platform.test")
        self.assertEqual(record["provider_name"], "custom_domain_temp_mail")

    def test_service_reads_messages_through_mailbox_descriptor(self):
        provider = _MailboxFirstProvider()
        with self.app.app_context():
            from outlook_web.repositories import temp_emails as temp_emails_repo
            from outlook_web.services.temp_mail_service import TempMailService

            temp_emails_repo.create_temp_email(
                email_addr="reader@service-platform.test",
                mailbox_type="user",
                visible_in_ui=True,
                meta={"provider_name": "custom_domain_temp_mail"},
            )
            service = TempMailService(provider_factory=lambda provider_name=None: provider)
            messages = service.list_messages("reader@service-platform.test", sync_remote=True)

        self.assertEqual(messages[0]["id"], "msg-1")
        self.assertEqual(provider.list_calls[0]["kind"], "temp")
        self.assertEqual(provider.list_calls[0]["provider_name"], "custom_domain_temp_mail")

    def test_delete_mailbox_skips_remote_delete_when_capability_disabled(self):
        provider = _MailboxFirstProvider()
        with self.app.app_context():
            from outlook_web.repositories import temp_emails as temp_emails_repo
            from outlook_web.services.temp_mail_service import TempMailService

            temp_emails_repo.create_temp_email(
                email_addr="delete-local@service-platform.test",
                mailbox_type="user",
                visible_in_ui=True,
                meta={
                    "provider_name": "custom_domain_temp_mail",
                    "provider_capabilities": {
                        "delete_mailbox": False,
                        "delete_message": True,
                        "clear_messages": True,
                    },
                },
            )
            service = TempMailService(provider_factory=lambda provider_name=None: provider)
            service.delete_mailbox("delete-local@service-platform.test")
            record = temp_emails_repo.get_temp_email_by_address("delete-local@service-platform.test")

        self.assertIsNone(record)
        self.assertEqual(provider.delete_mailbox_calls, [])
