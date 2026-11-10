from __future__ import annotations

import unittest
from unittest.mock import patch

from outlook_web.services import verification_extractor as extractor


class VerificationAiJsonContractTests(unittest.TestCase):
    def test_build_ai_input_payload_has_fixed_schema(self):
        payload = extractor.build_verification_ai_input_payload(
            {
                "subject": "Your code",
                "body": "code 123456",
                "body_html": "<p>code 123456</p>",
            },
            code_regex=r"\b\d{6}\b",
            code_length="6-6",
            code_source="all",
        )
        self.assertEqual(payload.get("schema_version"), "verification_ai_v1")
        self.assertEqual(payload.get("task"), "extract_verification")
        self.assertIn("mail", payload)
        self.assertIn("rules", payload)
        self.assertIn("hints", payload)
        self.assertIn("subject", payload["mail"])
        self.assertIn("text", payload["mail"])
        self.assertIn("html", payload["mail"])
        self.assertIn("code_regex", payload["rules"])
        self.assertIn("code_length", payload["rules"])
        self.assertIn("code_source", payload["hints"])

    @patch("outlook_web.services.verification_extractor.requests.post")
    def test_ai_invalid_json_response_falls_back_to_rule_result(self, mock_post):
        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "this is not json"}}]}

        mock_post.return_value = _Resp()

        with patch(
            "outlook_web.services.verification_extractor.get_verification_ai_runtime_config",
            return_value={
                "enabled": True,
                "base_url": "https://api.example.com/v1/chat/completions",
                "api_key": "sk-test",
                "model": "gpt-4.1-mini",
            },
        ):
            base = extractor.extract_verification_info_with_options(
                {"subject": "Code", "body": "Your code is 123456", "body_html": ""},
                code_length="6-6",
                code_source="all",
            )
            enhanced = extractor.enhance_verification_with_ai_fallback(
                email={
                    "subject": "Code",
                    "body": "Your code is 123456",
                    "body_html": "",
                },
                extracted=base,
                code_length="6-6",
                code_source="all",
            )

        self.assertEqual(enhanced.get("verification_code"), base.get("verification_code"))
        self.assertEqual(enhanced.get("verification_link"), base.get("verification_link"))

    @patch("outlook_web.services.verification_extractor.requests.post")
    def test_ai_link_does_not_override_when_code_exists(self, mock_post):
        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": '{"schema_version":"verification_ai_v1","verification_code":"998877","verification_link":"https://example.com/verify?t=1","confidence":"high","reason":"ok"}'
                            }
                        }
                    ]
                }

        mock_post.return_value = _Resp()

        with patch(
            "outlook_web.services.verification_extractor.get_verification_ai_runtime_config",
            return_value={
                "enabled": True,
                "base_url": "https://api.example.com/v1/chat/completions",
                "api_key": "sk-test",
                "model": "gpt-4.1-mini",
            },
        ):
            enhanced = extractor.enhance_verification_with_ai_fallback(
                email={
                    "subject": "misc",
                    "body": "random text",
                    "body_html": "",
                },
                extracted={
                    "verification_code": None,
                    "verification_link": "https://shop.example.com/deals",
                    "links": ["https://shop.example.com/deals"],
                    "formatted": "https://shop.example.com/deals",
                    "match_source": "all",
                    "confidence": "low",
                    "code_confidence": "low",
                    "link_confidence": "low",
                },
            )

        self.assertEqual(enhanced.get("verification_code"), "998877")
        self.assertIsNone(enhanced.get("verification_link"))
        self.assertEqual(enhanced.get("formatted"), "998877")


if __name__ == "__main__":
    unittest.main()
