from __future__ import annotations

import sqlite3
import time
from typing import Any, Dict, Optional


def acquire_distributed_lock(
    conn: sqlite3.Connection,
    name: str,
    owner_id: str,
    ttl_seconds: int,
) -> tuple[bool, Optional[Dict[str, Any]]]:
    """获取分布式锁（基于同一 SQLite 数据库），用于避免并发刷新冲突"""
    now_ts = time.time()
    expires_at = now_ts + ttl_seconds

    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT owner_id, acquired_at, expires_at
            FROM distributed_locks
            WHERE name = ?
            """,
            (name,),
        ).fetchone()

        if not row:
            conn.execute(
                """
                INSERT INTO distributed_locks (name, owner_id, acquired_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, owner_id, now_ts, expires_at),
            )
            conn.commit()
            return True, None

        if row["expires_at"] < now_ts:
            conn.execute(
                """
                UPDATE distributed_locks
                SET owner_id = ?, acquired_at = ?, expires_at = ?
                WHERE name = ?
                """,
                (owner_id, now_ts, expires_at, name),
            )
            conn.commit()
            return True, {
                "previous_owner_id": row["owner_id"],
                "previous_acquired_at": row["acquired_at"],
                "previous_expires_at": row["expires_at"],
            }

        conn.rollback()
        return False, {
            "owner_id": row["owner_id"],
            "acquired_at": row["acquired_at"],
            "expires_at": row["expires_at"],
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return False, {"error": str(e)}


def release_distributed_lock(conn: sqlite3.Connection, name: str, owner_id: str) -> bool:
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM distributed_locks WHERE name = ? AND owner_id = ?",
            (name, owner_id),
        )
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
