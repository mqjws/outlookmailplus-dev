from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from outlook_web.db import get_db

DELIVERY_STATUS_PROCESSING = "processing"
DELIVERY_STATUS_SENT = "sent"
DELIVERY_STATUS_FAILED = "failed"
DEFAULT_PROCESSING_TIMEOUT_SECONDS = 300


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def get_cursor(channel: str, source_type: str, source_key: str) -> str | None:
    db = get_db()
    row = db.execute(
        """
        SELECT last_cursor_value
        FROM notification_cursor_states
        WHERE channel = ? AND source_type = ? AND source_key = ?
        """,
        (channel, source_type, source_key),
    ).fetchone()
    return row["last_cursor_value"] if row and row["last_cursor_value"] else None


def upsert_cursor(channel: str, source_type: str, source_key: str, cursor_value: str) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO notification_cursor_states (
            channel, source_type, source_key, last_cursor_value, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(channel, source_type, source_key)
        DO UPDATE SET
            last_cursor_value = CASE
                WHEN notification_cursor_states.last_cursor_value = '' THEN excluded.last_cursor_value
                WHEN excluded.last_cursor_value = '' THEN notification_cursor_states.last_cursor_value
                WHEN notification_cursor_states.last_cursor_value >= excluded.last_cursor_value THEN notification_cursor_states.last_cursor_value
                ELSE excluded.last_cursor_value
            END,
            updated_at = CURRENT_TIMESTAMP
        """,
        (channel, source_type, source_key, cursor_value or ""),
    )
    db.commit()


def reset_channel_cursor(channel: str, source_type: str, source_key: str, cursor_value: str) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO notification_cursor_states (
            channel, source_type, source_key, last_cursor_value, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(channel, source_type, source_key)
        DO UPDATE SET
            last_cursor_value = excluded.last_cursor_value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (channel, source_type, source_key, cursor_value or ""),
    )
    db.commit()


def was_delivered(channel: str, source_type: str, source_key: str, message_id: str) -> bool:
    db = get_db()
    row = db.execute(
        """
        SELECT 1
        FROM notification_delivery_logs
        WHERE channel = ? AND source_type = ? AND source_key = ? AND message_id = ? AND status = ?
        """,
        (channel, source_type, source_key, message_id, DELIVERY_STATUS_SENT),
    ).fetchone()
    return row is not None


def claim_delivery_attempt(
    channel: str,
    source_type: str,
    source_key: str,
    message_id: str,
    *,
    processing_timeout_seconds: int = DEFAULT_PROCESSING_TIMEOUT_SECONDS,
) -> str:
    db = get_db()
    now_iso = _utc_now_iso()
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max(int(processing_timeout_seconds), 1))).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )

    cur = db.execute(
        """
        INSERT INTO notification_delivery_logs (
            channel, source_type, source_key, message_id, status, error_code, error_message, delivered_at, created_at
        )
        VALUES (?, ?, ?, ?, ?, '', '', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(channel, source_type, source_key, message_id) DO NOTHING
        """,
        (
            channel,
            source_type,
            source_key,
            message_id,
            DELIVERY_STATUS_PROCESSING,
            now_iso,
        ),
    )
    if cur.rowcount:
        db.commit()
        return "acquired"

    row = db.execute(
        """
        SELECT status, delivered_at
        FROM notification_delivery_logs
        WHERE channel = ? AND source_type = ? AND source_key = ? AND message_id = ?
        """,
        (channel, source_type, source_key, message_id),
    ).fetchone()
    if not row:
        db.commit()
        return "missing"

    current_status = str(row["status"] or "")
    delivered_at = str(row["delivered_at"] or "")
    can_reclaim = current_status == DELIVERY_STATUS_FAILED or (
        current_status == DELIVERY_STATUS_PROCESSING and delivered_at and delivered_at <= stale_cutoff
    )

    if can_reclaim:
        update = db.execute(
            """
            UPDATE notification_delivery_logs
            SET status = ?, error_code = '', error_message = '', delivered_at = ?
            WHERE channel = ? AND source_type = ? AND source_key = ? AND message_id = ?
              AND (
                    status = ?
                    OR (status = ? AND delivered_at <= ?)
                  )
            """,
            (
                DELIVERY_STATUS_PROCESSING,
                now_iso,
                channel,
                source_type,
                source_key,
                message_id,
                DELIVERY_STATUS_FAILED,
                DELIVERY_STATUS_PROCESSING,
                stale_cutoff,
            ),
        )
        if update.rowcount:
            db.commit()
            return "acquired"
        row = db.execute(
            """
            SELECT status
            FROM notification_delivery_logs
            WHERE channel = ? AND source_type = ? AND source_key = ? AND message_id = ?
            """,
            (channel, source_type, source_key, message_id),
        ).fetchone()
        current_status = str(row["status"] or "") if row else current_status

    db.commit()
    if current_status == DELIVERY_STATUS_SENT:
        return "sent"
    if current_status == DELIVERY_STATUS_PROCESSING:
        return "processing"
    if current_status == DELIVERY_STATUS_FAILED:
        return "failed"
    return "unknown"


def upsert_delivery_log(
    channel: str,
    source_type: str,
    source_key: str,
    message_id: str,
    *,
    status: str,
    error_code: str = "",
    error_message: str = "",
    delivered_at: str | None = None,
) -> None:
    db = get_db()
    delivered_at = delivered_at or _utc_now_iso()
    db.execute(
        """
        INSERT INTO notification_delivery_logs (
            channel, source_type, source_key, message_id, status, error_code, error_message, delivered_at, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(channel, source_type, source_key, message_id)
        DO UPDATE SET
            status = excluded.status,
            error_code = excluded.error_code,
            error_message = excluded.error_message,
            delivered_at = excluded.delivered_at
        """,
        (
            channel,
            source_type,
            source_key,
            message_id,
            status,
            error_code,
            error_message,
            delivered_at,
        ),
    )
    db.commit()


def complete_delivery_attempt(
    channel: str,
    source_type: str,
    source_key: str,
    message_id: str,
    *,
    status: str,
    error_code: str = "",
    error_message: str = "",
    delivered_at: str | None = None,
) -> None:
    upsert_delivery_log(
        channel,
        source_type,
        source_key,
        message_id,
        status=status,
        error_code=error_code,
        error_message=error_message,
        delivered_at=delivered_at,
    )


def cleanup_delivery_logs(*, retention_days: int = 14) -> None:
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%S")
    db.execute("DELETE FROM notification_delivery_logs WHERE delivered_at < ?", (cutoff,))
    db.commit()


def build_stable_message_key(
    *,
    source_type: str,
    source_key: str,
    message_id: str | None = None,
    subject: str | None = None,
    sender: str | None = None,
    received_at: str | None = None,
    preview: str | None = None,
    content: str | None = None,
) -> str:
    raw_message_id = str(message_id or "").strip()
    if raw_message_id:
        return raw_message_id

    payload = {
        "source_type": source_type,
        "source_key": (source_key or "").strip().lower(),
        "subject": (subject or "").strip(),
        "sender": (sender or "").strip(),
        "received_at": (received_at or "").strip(),
        "preview": (preview or "").strip(),
        "content": (content or "").strip()[:1000],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return f"fallback:{digest}"
