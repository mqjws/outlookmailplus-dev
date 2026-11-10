from __future__ import annotations

import unittest

from outlook_web.services.mailbox_resolver import normalize_alias_email


class TestNormalizeAliasEmail(unittest.TestCase):
    def test_plus_alias_stripped(self):
        self.assertEqual(
            normalize_alias_email("user+taobao@outlook.com"),
            "user@outlook.com",
        )

    def test_plus_alias_with_multiple_plus(self):
        self.assertEqual(
            normalize_alias_email("user+tag1+tag2@gmail.com"),
            "user@gmail.com",
        )

    def test_no_alias_unchanged(self):
        self.assertEqual(
            normalize_alias_email("user@outlook.com"),
            "user@outlook.com",
        )

    def test_empty_and_none(self):
        self.assertEqual(normalize_alias_email(""), "")
        self.assertEqual(normalize_alias_email(None), None)

    def test_invalid_format(self):
        self.assertEqual(normalize_alias_email("no-at-sign"), "no-at-sign")

    def test_case_preserved(self):
        self.assertEqual(
            normalize_alias_email("User+Tag@Outlook.COM"),
            "User@Outlook.COM",
        )

    def test_dots_before_plus_preserved(self):
        self.assertEqual(
            normalize_alias_email("first.last+tag@outlook.com"),
            "first.last@outlook.com",
        )
