from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import jsonify

from outlook_web import config
from outlook_web.db import create_sqlite_connection
from outlook_web.repositories import settings as settings_repo
from outlook_web.security.auth import login_required
from outlook_web.services.scheduler import REFRESH_LOCK_NAME


def utcnow() -> datetime:
    """返回 naive UTC 时间（等价于旧的 datetime.utcnow()）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==================== 调度器 API ====================


@login_required
def api_get_scheduler_status() -> Any:
    """获取调度器/定时刷新状态（用于验证"看起来已开启但实际未运行"的问题）"""
    conn = create_sqlite_connection()
    try:
        enable_scheduled = settings_repo.get_setting("enable_scheduled_refresh", "true").lower() == "true"
        use_cron = settings_repo.get_setting("use_cron_schedule", "false").lower() == "true"
        refresh_interval_days = int(settings_repo.get_setting("refresh_interval_days", "30"))
        refresh_cron = settings_repo.get_setting("refresh_cron", "0 2 * * *")

        # 心跳
        heartbeat_row = conn.execute("""
            SELECT value, updated_at
            FROM settings
            WHERE key = 'scheduler_heartbeat'
        """).fetchone()

        heartbeat = None
        heartbeat_age_seconds = None
        if heartbeat_row:
            try:
                heartbeat = json.loads(heartbeat_row["value"]) if heartbeat_row["value"] else None
            except Exception:
                heartbeat = {"raw": heartbeat_row["value"]}
            try:
                hb_time = datetime.fromisoformat(heartbeat_row["updated_at"])
                heartbeat_age_seconds = int((utcnow() - hb_time).total_seconds())
            except Exception:
                heartbeat_age_seconds = None

        # 锁状态
        lock_row = conn.execute(
            """
            SELECT owner_id, acquired_at, expires_at
            FROM distributed_locks
            WHERE name = ?
        """,
            (REFRESH_LOCK_NAME,),
        ).fetchone()
        now_ts = time.time()
        lock_info = None
        if lock_row and lock_row["expires_at"] and lock_row["expires_at"] > now_ts:
            lock_info = {
                "locked": True,
                "owner_id": lock_row["owner_id"],
                "acquired_at": lock_row["acquired_at"],
                "expires_at": lock_row["expires_at"],
            }
        else:
            lock_info = {"locked": False}

        # 最近一次定时刷新（含手动触发 scheduled_manual）
        last_scheduled_run = conn.execute("""
            SELECT id, trigger_source, status, started_at, finished_at,
                   total, success_count, failed_count, message, trace_id, requested_by_ip
            FROM refresh_runs
            WHERE trigger_source IN ('scheduled', 'scheduled_manual')
            ORDER BY started_at DESC
            LIMIT 1
        """).fetchone()

        last_scheduled = dict(last_scheduled_run) if last_scheduled_run else None

        running_run = conn.execute("""
            SELECT id, trigger_source, status, started_at, total, success_count, failed_count, trace_id
            FROM refresh_runs
            WHERE status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
        """).fetchone()

        running = dict(running_run) if running_run else None

        # 未来触发时间预览
        future_runs = []
        next_due = None
        if enable_scheduled:
            if use_cron:
                try:
                    from croniter import croniter

                    base_time = datetime.now()
                    it = croniter(refresh_cron, base_time)
                    for _ in range(5):
                        future_runs.append(it.get_next(datetime).isoformat())
                except Exception:
                    future_runs = []
            else:
                # 按天数策略：基于最近一次已完成的 scheduled/scheduled_manual 计算 next_due
                row = conn.execute("""
                    SELECT finished_at
                    FROM refresh_runs
                    WHERE trigger_source IN ('scheduled', 'scheduled_manual')
                      AND status IN ('completed', 'failed')
                      AND finished_at IS NOT NULL
                    ORDER BY finished_at DESC
                    LIMIT 1
                """).fetchone()
                last_finished_at = row["finished_at"] if row else None
                try:
                    last_time = datetime.fromisoformat(last_finished_at) if last_finished_at else None
                except Exception:
                    last_time = None

                base = last_time if last_time else utcnow()
                next_due_dt = base + timedelta(days=refresh_interval_days)
                next_due = next_due_dt.isoformat()
                future_runs.append(next_due_dt.isoformat())

        return jsonify(
            {
                "success": True,
                "scheduler": {
                    "autostart": config.get_scheduler_autostart_default(),
                    "enabled": enable_scheduled,
                    "use_cron": use_cron,
                    "refresh_cron": refresh_cron,
                    "refresh_interval_days": refresh_interval_days,
                    "future_runs": future_runs,
                    "next_due": next_due,
                    "heartbeat": heartbeat,
                    "heartbeat_updated_at": (heartbeat_row["updated_at"] if heartbeat_row else None),
                    "heartbeat_age_seconds": heartbeat_age_seconds,
                },
                "refresh": {
                    "lock": lock_info,
                    "running": running,
                    "last_scheduled": last_scheduled,
                },
            }
        )
    finally:
        conn.close()
