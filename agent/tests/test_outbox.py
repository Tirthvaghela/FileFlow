import json
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


def test_flush_outbox_does_not_repeat_a_failed_delivery_before_its_own_backoff_elapses(conn):
    """Distinct from the get_commands()-shape bug fixed in an earlier task
    (which had no per-item backoff at all, so the identical broken
    response was retried every single poll cycle): a flush_outbox()
    delivery failure is already gated behind bump_failure()'s own
    next_attempt_at for that specific row, independent of how many times
    flush_outbox() itself is called without any time passing. This is why
    poll_forever() previously discarding flush_outbox()'s return value
    (see test_commands.py's flush_outbox-health-signal tests) was a
    backoff-*timing* bug, not a "hammer the backend on every cycle" one."""
    outbox.enqueue_activity(conn, client_ref="a")
    calls = []

    class FakeClient:
        def report_activity(self, **kwargs):
            calls.append(kwargs)
            raise requests.exceptions.ConnectionError("offline")

    outbox.flush_outbox(FakeClient(), conn)
    outbox.flush_outbox(FakeClient(), conn)
    outbox.flush_outbox(FakeClient(), conn)

    assert len(calls) == 1, (
        "the item's own bump_failure()-driven backoff must suppress repeat delivery "
        "attempts regardless of how many times flush_outbox() itself is called"
    )
    assert len(outbox.due_items(conn, "activity", now=float("inf"))) == 1, "the item must remain queued"


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


# ---------------------------------------------------------------------------
# command_complete -- audited specifically because a completion reporting
# failure means something different from every other outbox kind: the
# underlying operation (undo/reclassify/organize_existing) has ALREADY
# physically happened by the time this item exists. Losing this item isn't
# "lose a report of something," it's "lose the ONLY record that a real
# operation already succeeded" -- and, uniquely for command_complete,
# losing it also destroys has_pending_completion()'s guard against the
# backend's still-"pending" command being redelivered and re-executed for
# real once the agent can talk to the backend again.
# ---------------------------------------------------------------------------


class _FakeCompleteClient:
    def __init__(self, exc=None):
        self._exc = exc
        self.calls = []

    def complete_command(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc


def test_successful_command_complete_removes_the_outbox_item(conn):
    outbox.enqueue_command_complete(conn, command_id=1, success=True, result={"destination_path": "C:/x"})
    client = _FakeCompleteClient()

    outbox.flush_outbox(client, conn)

    assert outbox.due_items(conn, "command_complete") == []
    assert client.calls == [
        {"command_id": 1, "success": True, "error": None, "result": {"destination_path": "C:/x"}}
    ]


def test_connection_failure_keeps_the_command_complete_item_queued(conn):
    outbox.enqueue_command_complete(conn, command_id=1, success=True)
    client = _FakeCompleteClient(exc=requests.exceptions.ConnectionError("offline"))

    outbox.flush_outbox(client, conn)

    # Still there, just backed off -- not due right now, but due shortly.
    assert outbox.due_items(conn, "command_complete") == []
    assert len(outbox.due_items(conn, "command_complete", now=time.time() + 100)) == 1


def test_command_complete_retry_eventually_succeeds(conn):
    item_id = outbox.enqueue_command_complete(conn, command_id=7, success=True, result={"scanned": 3})

    failing_client = _FakeCompleteClient(exc=requests.exceptions.ConnectionError("offline"))
    outbox.flush_outbox(failing_client, conn)
    assert len(outbox.due_items(conn, "command_complete", now=time.time() + 100)) == 1

    # bump_failure() pushed next_attempt_at real seconds into the future --
    # forcing it back to "due now" via direct SQL simulates the backoff
    # having elapsed, without an actual real-time sleep in the test.
    conn.execute("UPDATE outbox SET next_attempt_at = 0 WHERE id = ?", (item_id,))
    conn.commit()

    succeeding_client = _FakeCompleteClient()
    outbox.flush_outbox(succeeding_client, conn)

    assert outbox.due_items(conn, "command_complete") == []
    assert succeeding_client.calls == [
        {"command_id": 7, "success": True, "error": None, "result": {"scanned": 3}}
    ]


@pytest.mark.parametrize(
    "command_id,success,error,result",
    [
        (1, True, None, {}),  # undo -- never carries a result
        (2, True, None, {"destination_path": "C:/watch/Archive/report.pdf"}),  # reclassify
        (3, True, None, {"scanned": 5, "organized": 3, "duplicates": 1, "errors": 1}),  # organize_existing
        (4, False, "File no longer exists at C:/watch/x.pdf.", {}),  # any type, failed
    ],
)
def test_command_complete_payload_survives_a_failed_attempt_completely_unchanged(
    conn, command_id, success, error, result
):
    item_id = outbox.enqueue_command_complete(
        conn, command_id=command_id, success=success, error=error, result=result
    )
    outbox.flush_outbox(_FakeCompleteClient(exc=requests.exceptions.ConnectionError("offline")), conn)
    conn.execute("UPDATE outbox SET next_attempt_at = 0 WHERE id = ?", (item_id,))
    conn.commit()

    client = _FakeCompleteClient()
    outbox.flush_outbox(client, conn)

    assert client.calls == [
        {"command_id": command_id, "success": success, "error": error, "result": result}
    ]


def test_command_complete_survives_a_simulated_agent_restart(tmp_path):
    db_path = tmp_path / "restart_queue.db"
    conn = outbox.open_queue(db_path)
    outbox.enqueue_command_complete(conn, command_id=9, success=True, result={"destination_path": "C:/x"})
    conn.close()  # simulates the process exiting

    reopened = outbox.open_queue(db_path)  # simulates a fresh process starting back up
    assert len(outbox.due_items(reopened, "command_complete")) == 1

    client = _FakeCompleteClient()
    outbox.flush_outbox(client, reopened)

    assert outbox.due_items(reopened, "command_complete") == []
    assert client.calls == [{"command_id": 9, "success": True, "error": None, "result": {"destination_path": "C:/x"}}]


def test_repeated_completion_delivery_is_not_generated_by_the_outbox_itself(conn):
    """flush_outbox() only ever sends a due row once per pass and deletes it
    immediately on success, within the same _lock-protected section
    delete_item() uses -- there is no code path here that could enqueue or
    send the same command_complete row twice from a single successful
    delivery. (Whether the backend could ever receive a genuinely separate,
    second POST for the same command_id is a callers'-behavior question,
    already covered by has_pending_completion()'s own guard in commands.py
    and complete_command()'s own idempotent $set -- both audited
    separately; this test is scoped to the outbox's own delivery-once
    guarantee.)"""
    outbox.enqueue_command_complete(conn, command_id=1, success=True)
    client = _FakeCompleteClient()

    outbox.flush_outbox(client, conn)
    outbox.flush_outbox(client, conn)  # a second poll cycle, nothing left to send

    assert len(client.calls) == 1


@pytest.mark.parametrize("status_code", [401, 403])
def test_auth_error_keeps_the_command_complete_item_queued_instead_of_dropping_it(conn, status_code):
    """Regression test for a real, confirmed bug: _is_client_error()
    treated EVERY 4xx status identically, including 401 (agent token
    expired -- AGENT_TOKEN_EXPIRY is 365 days, so this is a real, eventual,
    expected occurrence, not a theoretical one -- or revoked via
    Settings' "regenerate token") and 403 (a read-only-scoped token,
    require_full_agent_scope) -- both entirely EXTERNALLY RECOVERABLE by
    reconfiguring the agent with a valid/full-scope token, unlike a
    genuinely malformed payload (422) that can never succeed no matter how
    many times it's retried.

    Treating 401/403 as "permanently broken, drop it" here silently
    destroyed the ONLY record that an already-completed undo/reclassify/
    organize_existing operation succeeded. Worse: because dropping this
    item also destroys has_pending_completion()'s guard (commands.py), the
    backend's still-"pending" command_id -- never told the outcome --
    gets redelivered to the agent once the token is fixed, and _handle()
    then RE-EXECUTES the same undo/reclassify/organize_existing a second
    time for real, since nothing local remains to suppress it."""
    outbox.enqueue_command_complete(conn, command_id=1, success=True, result={"destination_path": "C:/x"})
    client = _FakeCompleteClient(exc=_http_error(status_code))

    outbox.flush_outbox(client, conn)

    assert len(outbox.due_items(conn, "command_complete", now=time.time() + 100)) == 1, (
        f"a {status_code} is externally recoverable (reconfigure with a fresh/full-scope "
        "token) -- it must be retried, not treated as a permanently broken item"
    )


def test_422_still_permanently_drops_the_command_complete_item(conn):
    """Confirms the fix above did NOT weaken the genuinely-correct existing
    policy for a truly unrecoverable item -- a 422 (the request body
    itself is permanently malformed relative to the backend's schema)
    must still be dropped, exactly as before."""
    outbox.enqueue_command_complete(conn, command_id=1, success=True)
    client = _FakeCompleteClient(exc=_http_error(422))

    outbox.flush_outbox(client, conn)

    assert outbox.due_items(conn, "command_complete", now=time.time() + 100) == []


def test_404_still_permanently_drops_the_command_complete_item(conn):
    """A 404 here means the command_id genuinely doesn't map to a row this
    agent's own account can complete (never happens in normal operation,
    since command_id always comes from this same account's own GET
    /api/agent/commands response moments earlier) -- retrying the exact
    same command_id can never succeed, so dropping it is correct."""
    outbox.enqueue_command_complete(conn, command_id=1, success=True)
    client = _FakeCompleteClient(exc=_http_error(404))

    outbox.flush_outbox(client, conn)

    assert outbox.due_items(conn, "command_complete", now=time.time() + 100) == []


# ---------------------------------------------------------------------------
# has_pending_completion() -- the guard commands.py::_handle() checks before
# running a command's handler a second time. Audited specifically for the
# backoff boundary: due_items(conn, "command_complete", now=float("inf"))
# is meant to answer "does a completion record still exist for this
# command" (true regardless of how far in the future next_attempt_at sits),
# never "is it currently due for delivery" -- those are two different
# questions, and due_items() itself is what flush_outbox() uses for the
# second one. No direct test of has_pending_completion() existed before
# this task -- it was only ever exercised indirectly, and only in the
# "freshly queued, never yet flushed" case (see
# test_commands.py::test_handle_does_not_rerun_a_command_whose_report_is_
# still_queued), never through an actual backoff cycle.
# ---------------------------------------------------------------------------


def test_has_pending_completion_true_for_a_freshly_queued_item(conn):
    outbox.enqueue_command_complete(conn, command_id=1, success=True)
    assert outbox.has_pending_completion(conn, 1) is True


def test_has_pending_completion_true_while_backed_off_a_few_seconds(conn):
    item_id = outbox.enqueue_command_complete(conn, command_id=1, success=True)
    outbox.bump_failure(conn, item_id)  # ~5s backoff
    assert outbox.has_pending_completion(conn, 1) is True


def test_has_pending_completion_true_while_backed_off_several_minutes(conn):
    item_id = outbox.enqueue_command_complete(conn, command_id=1, success=True)
    conn.execute("UPDATE outbox SET next_attempt_at = ? WHERE id = ?", (time.time() + 300, item_id))
    conn.commit()
    assert outbox.has_pending_completion(conn, 1) is True


def test_has_pending_completion_true_when_backed_off_much_further_still(conn):
    item_id = outbox.enqueue_command_complete(conn, command_id=1, success=True)
    conn.execute("UPDATE outbox SET next_attempt_at = ? WHERE id = ?", (time.time() + 100_000, item_id))
    conn.commit()
    assert outbox.has_pending_completion(conn, 1) is True


def test_has_pending_completion_false_with_no_command_complete_rows_at_all(conn):
    assert outbox.has_pending_completion(conn, 1) is False


def test_has_pending_completion_false_when_only_unrelated_kinds_are_queued(conn):
    outbox.enqueue_activity(conn, client_ref="x")
    outbox.enqueue_pending_file(conn, "C:/some/path.txt")
    assert outbox.has_pending_completion(conn, 1) is False


def test_has_pending_completion_false_for_a_different_command_id(conn):
    outbox.enqueue_command_complete(conn, command_id=1, success=True)
    assert outbox.has_pending_completion(conn, 2) is False


def test_has_pending_completion_false_once_the_item_is_delivered_and_removed(conn):
    outbox.enqueue_command_complete(conn, command_id=1, success=True)
    outbox.flush_outbox(_FakeCompleteClient(), conn)
    assert outbox.has_pending_completion(conn, 1) is False


def test_has_pending_completion_isolates_multiple_commands_independently(conn):
    id_a = outbox.enqueue_command_complete(conn, command_id=10, success=True)
    outbox.enqueue_command_complete(conn, command_id=20, success=True)

    assert outbox.has_pending_completion(conn, 10) is True
    assert outbox.has_pending_completion(conn, 20) is True

    outbox.delete_item(conn, id_a)

    assert outbox.has_pending_completion(conn, 10) is False, "removing A's completion must not affect B"
    assert outbox.has_pending_completion(conn, 20) is True


def test_has_pending_completion_remains_true_after_a_401_bumps_it_into_backoff(conn):
    outbox.enqueue_command_complete(conn, command_id=1, success=True)
    outbox.flush_outbox(_FakeCompleteClient(exc=_http_error(401)), conn)
    assert outbox.has_pending_completion(conn, 1) is True


def test_has_pending_completion_remains_true_after_a_403_bumps_it_into_backoff(conn):
    outbox.enqueue_command_complete(conn, command_id=1, success=True)
    outbox.flush_outbox(_FakeCompleteClient(exc=_http_error(403)), conn)
    assert outbox.has_pending_completion(conn, 1) is True


def test_has_pending_completion_remains_true_after_a_connection_failure_bumps_it_into_backoff(conn):
    outbox.enqueue_command_complete(conn, command_id=1, success=True)
    outbox.flush_outbox(_FakeCompleteClient(exc=requests.exceptions.ConnectionError("offline")), conn)
    assert outbox.has_pending_completion(conn, 1) is True


def test_has_pending_completion_survives_a_simulated_agent_restart_while_backed_off(tmp_path):
    db_path = tmp_path / "restart_guard.db"
    conn = outbox.open_queue(db_path)
    item_id = outbox.enqueue_command_complete(conn, command_id=1, success=True)
    conn.execute("UPDATE outbox SET next_attempt_at = ? WHERE id = ?", (time.time() + 300, item_id))
    conn.commit()
    conn.close()  # simulates the process exiting mid-backoff

    reopened = outbox.open_queue(db_path)  # simulates a fresh process starting back up
    assert outbox.has_pending_completion(reopened, 1) is True


def test_reclassify_result_survives_a_backoff_cycle_intact_under_has_pending_completion(conn):
    dest = "C:/watch/Archive/report.pdf"
    outbox.enqueue_command_complete(conn, command_id=1, success=True, result={"destination_path": dest})

    outbox.flush_outbox(_FakeCompleteClient(exc=requests.exceptions.ConnectionError("offline")), conn)

    assert outbox.has_pending_completion(conn, 1) is True
    row = outbox.due_items(conn, "command_complete", now=float("inf"))[0]
    assert json.loads(row["payload"])["result"] == {"destination_path": dest}
