"""Durable local outbox -- so a physical action the agent already took
(a file moved, a command executed) is never silently lost just because the
HTTP call reporting it back to the backend happened to fail. Backed by a
plain SQLite file (stdlib, no new dependency) so it survives both a
transient network blip and an agent process restart -- reopening the same
file picks up right where it left off.
"""

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path

import requests

logger = logging.getLogger("fileflow.agent.outbox")

DB_PATH = Path(__file__).resolve().parent / "agent_queue.db"

_BASE_BACKOFF_SECONDS = 5.0
_MAX_BACKOFF_SECONDS = 300.0

_lock = threading.Lock()


def open_queue(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            payload TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at REAL NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    return conn


def enqueue(conn: sqlite3.Connection, kind: str, payload: dict) -> int:
    with _lock:
        cur = conn.execute(
            "INSERT INTO outbox (kind, payload, next_attempt_at) VALUES (?, ?, 0)",
            (kind, json.dumps(payload)),
        )
        conn.commit()
        return cur.lastrowid


def enqueue_activity(conn: sqlite3.Connection, **fields) -> int:
    return enqueue(conn, "activity", fields)


def enqueue_command_complete(
    conn: sqlite3.Connection,
    command_id: int,
    success: bool,
    error: str | None = None,
    result: dict | None = None,
) -> int:
    return enqueue(
        conn,
        "command_complete",
        {"command_id": command_id, "success": success, "error": error, "result": result or {}},
    )


def enqueue_pending_file(conn: sqlite3.Connection, path: Path) -> int:
    return enqueue(conn, "pending_file", {"path": str(path)})


def due_items(conn: sqlite3.Connection, kind: str, now: float | None = None) -> list[sqlite3.Row]:
    now = now if now is not None else time.time()
    with _lock:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT id, payload, attempts FROM outbox WHERE kind = ? AND next_attempt_at <= ? ORDER BY id",
            (kind, now),
        ).fetchall()


def delete_item(conn: sqlite3.Connection, item_id: int) -> None:
    with _lock:
        conn.execute("DELETE FROM outbox WHERE id = ?", (item_id,))
        conn.commit()


def bump_failure(conn: sqlite3.Connection, item_id: int) -> None:
    with _lock:
        row = conn.execute("SELECT attempts FROM outbox WHERE id = ?", (item_id,)).fetchone()
        attempts = (row[0] if row else 0) + 1
        delay = min(_BASE_BACKOFF_SECONDS * (2 ** (attempts - 1)), _MAX_BACKOFF_SECONDS)
        conn.execute(
            "UPDATE outbox SET attempts = ?, next_attempt_at = ? WHERE id = ?",
            (attempts, time.time() + delay, item_id),
        )
        conn.commit()


def _is_client_error(exc: requests.exceptions.RequestException) -> bool:
    response = getattr(exc, "response", None)
    return response is not None and 400 <= response.status_code < 500


def _log_if_auth_error(exc: requests.exceptions.RequestException) -> None:
    response = getattr(exc, "response", None)
    if response is None or response.status_code not in (401, 403):
        return
    if response.status_code == 403:
        # Distinct from 401: the token is still valid, it just wasn't
        # minted with enough scope for this action -- e.g. a "Read-only"
        # token can fetch rules but can't report activity or run commands.
        # Reconfigure with a "Full control" token from Settings to fix it.
        logger.error(
            "Agent token doesn't have permission for this action -- it may be a "
            "Read-only token. Generate a Full control token from Settings and "
            "reconfigure the agent (tray icon -> Reconfigure)."
        )
    else:
        logger.error(
            "Agent token rejected (401) -- it may have been revoked. Generate a "
            "fresh token from Settings and reconfigure the agent (tray icon -> Reconfigure)."
        )


def _flush_kind(client, conn: sqlite3.Connection, kind: str, sender) -> bool:
    """Sends every due row of this kind via `sender(payload_dict)`. Returns
    False (and stops) on the first connection-level failure -- everything
    behind it is almost certainly unreachable too, so there's no point
    trying each one individually. A 4xx is a different story: that one
    row is broken (bad payload, schema drift against a newer/older
    backend) and will never succeed no matter how many times it's retried,
    so it's dropped and the rest of the queue keeps flushing."""
    for row in due_items(conn, kind):
        payload = json.loads(row["payload"])
        try:
            sender(payload)
            delete_item(conn, row["id"])
        except requests.exceptions.RequestException as exc:
            if _is_client_error(exc):
                logger.error("Dropping unrecoverable %s item %s: %s", kind, row["id"], exc)
                _log_if_auth_error(exc)
                delete_item(conn, row["id"])
                continue
            bump_failure(conn, row["id"])
            return False
    return True


def flush_outbox(client, conn: sqlite3.Connection) -> None:
    if not _flush_kind(client, conn, "activity", lambda p: client.report_activity(**p)):
        return
    _flush_kind(client, conn, "command_complete", lambda p: client.complete_command(**p))
