import unittest


class TestImapGenericAuthMessages(unittest.TestCase):
    def test_outlook_basic_auth_blocked_message_is_normalized(self):
        from outlook_web.services.imap_generic import _normalize_imap_auth_error_message

        raw = (
            "b'[AUTHENTICATIONFAILED] AuthFailed:LogonDenied-BasicAuthBlocked-"
            "<UserType:OutlookCom> LogonFailed-BasicAuthBlocked'"
        )
        message = _normalize_imap_auth_error_message(raw, provider="outlook", imap_host="outlook.live.com")
        self.assertIn("Outlook.com 已阻止 Basic Auth", message)
        self.assertIn("Outlook OAuth", message)

    def test_gmail_message_keeps_app_password_hint(self):
        from outlook_web.services.imap_generic import _normalize_imap_auth_error_message

        message = _normalize_imap_auth_error_message("AUTH failed", provider="gmail", imap_host="imap.gmail.com")
        self.assertIn("应用专用密码", message)


if __name__ == "__main__":
    unittest.main()
