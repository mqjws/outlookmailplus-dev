"""
手工联调用验证脚本：验证码 AI 相关接口返回内容探测。

用途：
1) 登录并读取 /api/settings，确认运行期 AI 配置状态
2) 调用 /api/settings/verification-ai-test，查看连通性与契约结果
3) 调用 /api/emails/<email>/extract-verification，查看端到端提取返回

可选环境变量：
- OEP_BASE_URL         默认 http://127.0.0.1:5000
- OEP_LOGIN_PASSWORD   默认从 .env 读取 LOGIN_PASSWORD
- OEP_TARGET_EMAIL     默认自动取 /api/accounts 第一条邮箱
"""

from __future__ import annotations

import json
import os
import urllib.parse
from pathlib import Path
from typing import Any

import requests


def _read_login_password_from_env_file() -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            if text.startswith("LOGIN_PASSWORD="):
                return text.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _pretty(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception:
        return str(data)


def _mask(value: str, head: int = 4, tail: int = 4) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    if len(raw) <= head + tail:
        return "*" * len(raw)
    return raw[:head] + ("*" * (len(raw) - head - tail)) + raw[-tail:]


def main() -> None:
    base_url = os.getenv("OEP_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    login_password = os.getenv("OEP_LOGIN_PASSWORD") or _read_login_password_from_env_file()
    target_email = (os.getenv("OEP_TARGET_EMAIL") or "").strip()

    if not login_password:
        raise SystemExit("❌ 未提供登录密码：请设置 OEP_LOGIN_PASSWORD 或在 .env 中配置 LOGIN_PASSWORD")

    s = requests.Session()
    # 避免被系统代理干扰本地联调
    s.trust_env = False

    print("=" * 72)
    print("[1/6] 登录")
    login_resp = s.post(
        f"{base_url}/login",
        json={"password": login_password},
        timeout=10,
    )
    print("status:", login_resp.status_code)
    print(_pretty(login_resp.json()))

    print("=" * 72)
    print("[2/6] 获取 settings（AI 关键字段）")
    settings_resp = s.get(f"{base_url}/api/settings", timeout=15)
    settings_json = settings_resp.json()
    settings = settings_json.get("settings") or {}
    settings_view = {
        "verification_ai_enabled": settings.get("verification_ai_enabled"),
        "verification_ai_base_url": settings.get("verification_ai_base_url"),
        "verification_ai_model": settings.get("verification_ai_model"),
        "verification_ai_api_key_set": settings.get("verification_ai_api_key_set"),
        "verification_ai_api_key_masked": settings.get("verification_ai_api_key_masked"),
    }
    print("status:", settings_resp.status_code)
    print(_pretty(settings_view))

    print("=" * 72)
    print("[3/6] 获取 CSRF token")
    csrf_resp = s.get(f"{base_url}/api/csrf-token", timeout=10)
    csrf_data = csrf_resp.json()
    csrf_token = csrf_data.get("csrf_token")
    print("status:", csrf_resp.status_code)
    print(
        _pretty(
            {
                "csrf_token": _mask(csrf_token),
                "csrf_disabled": csrf_data.get("csrf_disabled"),
            }
        )
    )

    print("=" * 72)
    print("[4/6] 调用 AI 探测接口 /api/settings/verification-ai-test")
    headers = {"Content-Type": "application/json"}
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
    ai_test_resp = s.post(
        f"{base_url}/api/settings/verification-ai-test",
        json={},
        headers=headers,
        timeout=20,
    )
    ai_test_json = ai_test_resp.json()
    print("status:", ai_test_resp.status_code)
    print(_pretty(ai_test_json))

    print("=" * 72)
    print("[5/6] 获取账号列表，确定目标邮箱")
    accounts_resp = s.get(f"{base_url}/api/accounts", timeout=20)
    accounts_json = accounts_resp.json()
    accounts = accounts_json.get("accounts") or []
    if not target_email and accounts:
        target_email = str(accounts[0].get("email") or "").strip()
    print("status:", accounts_resp.status_code)
    print(_pretty({"accounts_count": len(accounts), "target_email": target_email}))

    if not target_email:
        raise SystemExit("❌ 未找到可测试邮箱，请设置 OEP_TARGET_EMAIL")

    print("=" * 72)
    print("[6/6] 调用提取接口 /api/emails/<email>/extract-verification")
    email_q = urllib.parse.quote(target_email, safe="")
    extract_url = f"{base_url}/api/emails/{email_q}/extract-verification?code_source=all"
    extract_resp = s.get(extract_url, timeout=45)
    extract_json = extract_resp.json()
    print("status:", extract_resp.status_code)
    print(_pretty(extract_json))

    print("=" * 72)
    print("✅ 探测完成")


if __name__ == "__main__":
    main()
