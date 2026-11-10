from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from outlook_web.db import get_db


def encode_temp_mail_log_account_id(temp_mail_id: Any) -> Optional[int]:
    # 用负数编码临时邮箱 ID，与 accounts 表正数 ID 区分，使 JOIN 条件可用 account_id > 0 / < 0 一刀切
    try:
        value = int(temp_mail_id or 0)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return -value


def resolve_extract_log_outcome(result: Optional[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    # 优先级：code > link > none；result 可能是 None（异常路径），需防御
    payload = dict(result or {})
    code = str(payload.get("verification_code") or "").strip()
    if code:
        return "code", code

    link = str(payload.get("verification_link") or "").strip()
    if link:
        return "link", link

    formatted = str(payload.get("formatted") or "").strip()
    return "none", formatted or None


def write_verification_extract_log(
    *,
    account_id: Optional[int],
    channel: str,
    started_at: float,
    finished_at: float,
    result_type: str,
    code_found: Optional[str],
    used_ai: bool,
    error_code: Optional[str],
    trace_id: Optional[str],
    db: Any = None,
) -> None:
    try:
        normalized_account_id = int(account_id) if account_id is not None else None
    except (TypeError, ValueError):
        normalized_account_id = None

    if normalized_account_id is None:
        return

    try:
        conn = db or get_db()
        conn.execute(
            """
            INSERT INTO verification_extract_logs (
                account_id,
                channel,
                started_at,
                finished_at,
                duration_ms,
                result_type,
                code_found,
                used_ai,
                error_code,
                trace_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_account_id,
                str(channel or "unknown"),
                float(started_at or 0),
                float(finished_at or 0),
                max(int(round((float(finished_at or 0) - float(started_at or 0)) * 1000)), 0),
                str(result_type or "none"),
                code_found,
                1 if used_ai else 0,
                error_code,
                trace_id,
            ),
        )
        conn.commit()
    except Exception:
        # 日志写入失败不应阻断业务主链路（如邮件读取、验证码提取），因此静默吞掉
        pass
