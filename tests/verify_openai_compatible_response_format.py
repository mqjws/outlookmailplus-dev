"""
验证 OpenAI 兼容接口的返回格式能力（response_format / tools）。

用途：对当前配置的 OpenAI 兼容端点做协议探测，观察不同请求体下返回结构：
1) response_format = json_object
2) response_format = json_schema（严格模式）
3) 不带 response_format
4) tools + tool_choice（函数调用）

运行：
    python tests/verify_openai_compatible_response_format.py

可选环境变量：
    OEP_PROBE_MODEL=deepseek-ai/DeepSeek-V3.2
    OEP_PROBE_TIMEOUT=20
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests

from outlook_web.repositories import settings as settings_repo
from outlook_web.services.verification_extractor import (
    _normalize_verification_ai_endpoint,
)
from web_outlook_app import app


def _preview_text(value: Any, limit: int = 400) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + " ...<truncated>"


def _build_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "string", "enum": ["verification_ai_v1"]},
            "verification_code": {"type": "string"},
            "verification_link": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "low"]},
            "reason": {"type": "string"},
        },
        "required": [
            "schema_version",
            "verification_code",
            "verification_link",
            "confidence",
            "reason",
        ],
    }


def _extract_shape(payload: dict[str, Any]) -> dict[str, Any]:
    keys = list(payload.keys())[:20] if isinstance(payload, dict) else []
    choices = payload.get("choices") if isinstance(payload, dict) else None
    choices_type = type(choices).__name__ if choices is not None else "None"

    first_message_content = None
    first_tool_calls = None
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        msg = choices[0].get("message")
        if isinstance(msg, dict):
            first_message_content = msg.get("content")
            first_tool_calls = msg.get("tool_calls")

    return {
        "top_keys": keys,
        "object": payload.get("object") if isinstance(payload, dict) else None,
        "model": payload.get("model") if isinstance(payload, dict) else None,
        "choices_type": choices_type,
        "choices_is_empty_list": choices == [] if isinstance(choices, list) else False,
        "has_error_field": isinstance(payload, dict) and ("error" in payload),
        "error_field": payload.get("error") if isinstance(payload, dict) else None,
        "first_message_content_preview": _preview_text(first_message_content),
        "first_tool_calls_preview": _preview_text(first_tool_calls),
    }


def main() -> None:
    timeout_seconds = int(os.getenv("OEP_PROBE_TIMEOUT", "20"))

    with app.app_context():
        base_url = settings_repo.get_verification_ai_base_url()
        api_key = settings_repo.get_verification_ai_api_key()
        saved_model = settings_repo.get_verification_ai_model()

    endpoint = _normalize_verification_ai_endpoint(base_url)
    model = os.getenv("OEP_PROBE_MODEL", saved_model)

    if not endpoint or not api_key or not model:
        raise SystemExit("❌ 配置不完整：需要 base_url/api_key/model")

    schema = _build_schema()
    base_messages = [
        {
            "role": "system",
            "content": (
                "你是验证码提取器。请仅输出 JSON，字段为 "
                "schema_version, verification_code, verification_link, confidence, reason。"
            ),
        },
        {
            "role": "user",
            "content": "邮件内容：Your verification code is 123456",
        },
    ]

    scenarios: list[tuple[str, dict[str, Any]]] = [
        (
            "json_object",
            {
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": base_messages,
            },
        ),
        (
            "json_schema_strict",
            {
                "model": model,
                "temperature": 0,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "verification_result",
                        "schema": schema,
                        "strict": True,
                    },
                },
                "messages": base_messages,
            },
        ),
        (
            "no_response_format",
            {
                "model": model,
                "temperature": 0,
                "messages": base_messages,
            },
        ),
        (
            "tools_function_call",
            {
                "model": model,
                "temperature": 0,
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "return_verification",
                            "description": "返回验证码结构",
                            "parameters": schema,
                        },
                    }
                ],
                "tool_choice": {
                    "type": "function",
                    "function": {"name": "return_verification"},
                },
                "messages": base_messages,
            },
        ),
    ]

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    print("=" * 88)
    print("endpoint:", endpoint)
    print("model:", model)
    print("timeout_seconds:", timeout_seconds)
    print("=" * 88)

    results: list[dict[str, Any]] = []
    for name, body in scenarios:
        item: dict[str, Any] = {"scenario": name}
        try:
            resp = requests.post(
                endpoint,
                headers=headers,
                json=body,
                timeout=timeout_seconds,
            )
            item["http_status"] = resp.status_code
            item["response_text_preview"] = _preview_text(resp.text, limit=500)

            try:
                payload = resp.json()
                item["json_parse_ok"] = True
                item.update(_extract_shape(payload))
            except Exception as exc:
                item["json_parse_ok"] = False
                item["json_parse_error"] = str(exc)
        except Exception as exc:
            item["request_error"] = str(exc)

        results.append(item)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
