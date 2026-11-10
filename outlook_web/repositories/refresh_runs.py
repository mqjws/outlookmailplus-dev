from __future__ import annotations

import sqlite3
import uuid
from typing import Optional


def create_refresh_run(
    conn: sqlite3.Connection,
    trigger_source: str,
    trace_id: str,
    requested_by_ip: str = None,
    requested_by_user_agent: str = None,
    total: int = 0,
) -> str:
    run_id = uuid.uuid4().hex
    conn.execute(
        """
        INSERT INTO refresh_runs (
            id, trigger_source, status,
            requested_by_ip, requested_by_user_agent,
            total, success_count, failed_count,
            trace_id
        ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)
        """,
        (
            run_id,
            trigger_source,
            "running",
            requested_by_ip,
            requested_by_user_agent,
            total,
            trace_id,
        ),
    )
    conn.commit()
    return run_id


def finish_refresh_run(
    conn: sqlite3.Connection,
    run_id: str,
    status: str,
    total: int,
    success_count: int,
    failed_count: int,
    message: str = None,
):
    conn.execute(
        """
        UPDATE refresh_runs
        SET status = ?, finished_at = CURRENT_TIMESTAMP,
            total = ?, success_count = ?, failed_count = ?, message = ?
        WHERE id = ?
        """,
        (status, total, success_count, failed_count, message, run_id),
    )
    conn.commit()
