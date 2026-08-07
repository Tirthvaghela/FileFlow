import time

import pytest
import requests

from agent import outbox


@pytest.fixture
def conn(tmp_path):
    return outbox.open_queue(tmp_path / "test_outbox.db")


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
