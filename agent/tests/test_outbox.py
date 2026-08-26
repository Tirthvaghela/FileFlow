import time

import pytest
import requests

from agent import outbox


@pytest.fixture
def conn(tmp_path):
    return outbox.open_queue(tmp_path / "test_outbox.db")


def test_open_queue_recovers_from_a_corrupted_database_file(tmp_path):
    """Regression test for a real, confirmed bug: open_queue() had no
    try/except around CREATE TABLE, so a genuinely corrupt/non-SQLite file
    at the outbox's path (disk corruption, external interference) raised
    an uncaught sqlite3.DatabaseError -- crashing the whole agent before
    main() got anywhere near showing a tray icon or notification, the same
    "silent death, no console, no clue why" pattern already fixed this
    session for config.json and rules_cache.json. Unlike those, nothing
    here needs the user's input to recover -- the outbox only holds
    not-yet-delivered reports, not the underlying file-organizing work --
    so open_queue() now starts fresh automatically instead of crashing."""
    path = tmp_path / "corrupt.db"
    path.write_text("this is not a sqlite database file at all, just garbage text")

    conn = outbox.open_queue(path)  # must not raise

    # The fresh queue must be genuinely usable afterward.
    item_id = outbox.enqueue_activity(conn, client_ref="x")
    assert [row["id"] for row in outbox.due_items(conn, "activity")] == [item_id]


def test_enqueue_is_immediately_due(conn):
    item_id = outbox.enqueue_activity(conn, original_filename="a.txt")
    due = outbox.due_items(conn, "activity")
    assert [row["id"] for row in due] == [item_id]


def test_delete_item_removes_it(conn):
    item_id = outbox.enqueue_pending_file(conn, "C:/some/path.txt")
    outbox.delete_item(conn, item_id)
    assert outbox.due_items(conn, "pending_file") == []


def test_bump_failure_delays_next_attempt(conn):
    item_id = outbox.enqueue_command_complete(conn, command_id=1, success=True)
    outbox.bump_failure(conn, item_id)
    # Not due right now (backoff pushed it into the future)...
    assert outbox.due_items(conn, "command_complete", now=time.time()) == []
    # ...but is due once that time has passed.
    assert outbox.due_items(conn, "command_complete", now=time.time() + 10) != []


def test_bump_failure_increases_delay_with_repeated_attempts(conn):
    item_id = outbox.enqueue_command_complete(conn, command_id=1, success=True)
    outbox.bump_failure(conn, item_id)  # attempt 1: ~5s
    first_due = conn.execute(
        "SELECT next_attempt_at FROM outbox WHERE id = ?", (item_id,)
    ).fetchone()[0]
    outbox.bump_failure(conn, item_id)  # attempt 2: ~10s
    second_due = conn.execute(
        "SELECT next_attempt_at FROM outbox WHERE id = ?", (item_id,)
    ).fetchone()[0]
    assert second_due > first_due


def test_bump_failure_does_not_overflow_after_thousands_of_consecutive_failures(conn):
    """Regression test for a real, confirmed bug: 2 ** (attempts - 1) was
    computed in full before being handed to min(..., _MAX_BACKOFF_SECONDS),
    so an item stuck failing for ~3.5+ continuous days (reachable by pure
    time passing against a permanently unreachable backend -- attempts is
    persisted here, so it's never reset, including across a process
    restart; no manual tampering needed) hit a Python int too large for
    float() to represent, and bump_failure() raised an uncaught
    OverflowError -- confirmed directly at attempts=1025 -- instead of
    just applying the same _MAX_BACKOFF_SECONDS cap every other large
    attempts count already got. Jumping straight to attempts=1024 here
    (instead of 1024 real sequential calls) reproduces the exact same
    real code path -- SQLite doesn't care how attempts got to that value,
    only bump_failure()'s own arithmetic does."""
    item_id = outbox.enqueue_command_complete(conn, command_id=1, success=True)
    conn.execute("UPDATE outbox SET attempts = 1024 WHERE id = ?", (item_id,))
    conn.commit()

    outbox.bump_failure(conn, item_id)  # must not raise OverflowError

    row = conn.execute(
        "SELECT attempts, next_attempt_at FROM outbox WHERE id = ?", (item_id,)
    ).fetchone()
    assert row[0] == 1025
    delay = row[1] - time.time()
    assert 250 < delay <= outbox._MAX_BACKOFF_SECONDS, "must still apply the normal max backoff cap"


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def _http_error(status_code):
    exc = requests.exceptions.HTTPError()
    exc.response = _FakeResponse(status_code)
    return exc


def test_flush_outbox_stops_on_connection_error(conn):
    outbox.enqueue_activity(conn, client_ref="a")
    outbox.enqueue_activity(conn, client_ref="b")

    class FakeClient:
        def report_activity(self, **kwargs):
            raise requests.exceptions.ConnectionError("offline")

    outbox.flush_outbox(FakeClient(), conn)
    # Nothing delivered, both items still queued (just backed off).
    assert len(outbox.due_items(conn, "activity", now=time.time() + 100)) == 2


def test_flush_outbox_drops_unrecoverable_client_error(conn):
    outbox.enqueue_activity(conn, client_ref="broken")
    outbox.enqueue_activity(conn, client_ref="fine")
    delivered = []

    class FakeClient:
        def report_activity(self, **kwargs):
            if kwargs.get("client_ref") == "broken":
                raise _http_error(422)
            delivered.append(kwargs["client_ref"])

    outbox.flush_outbox(FakeClient(), conn)
    assert delivered == ["fine"]
    assert outbox.due_items(conn, "activity") == []


def test_flush_outbox_delivers_and_clears_on_success(conn):
    outbox.enqueue_activity(conn, client_ref="ok")
    delivered = []

    class FakeClient:
        def report_activity(self, **kwargs):
            delivered.append(kwargs)

    outbox.flush_outbox(FakeClient(), conn)
    assert delivered == [{"client_ref": "ok"}]
    assert outbox.due_items(conn, "activity") == []
