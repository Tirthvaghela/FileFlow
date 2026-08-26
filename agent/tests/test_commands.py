import json
import time
from pathlib import Path

import pytest
import requests

from agent import commands, outbox, rules_cache
from agent.watcher import _consume_self_move
from config.settings import settings


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def _http_error(status_code):
    exc = requests.exceptions.HTTPError()
    exc.response = _FakeResponse(status_code)
    return exc

_ORGANIZE_RULES = {
    "categories": {"Documents": [".pdf", ".txt"], "Images": [".jpg"]},
    "extension_rules": {},
    "keyword_rules": [],
    "regex_rules": [],
    "content_keyword_rules": [],
    "date_rules": [],
    "large_file_enabled": False,
    "large_file_threshold_mb": 500,
    "large_file_folder": "Large Files",
    "default_category": "Others",
    "auto_organize_unknown_extensions": True,
    "duplicate_handling": "rename",
    "enable_timestamp_rename": False,
    "timestamp_rename_categories": [],
}


class _OrganizeRulesClient:
    def get_rules(self):
        return _ORGANIZE_RULES


@pytest.fixture(autouse=True)
def _isolated_rules_cache_for_organize_existing(tmp_path, monkeypatch):
    # _do_organize_existing() reaches rules_cache.get_rules() -- isolate it
    # the same way test_watcher.py/test_rules_cache.py already do, so these
    # tests never touch the real cache file next to the module.
    monkeypatch.setattr(rules_cache, "CACHE_PATH", tmp_path / "rules_cache.json")
    # Real stability-poll loop, just fast -- same reasoning as test_watcher.
    # py's watch_root fixture; it isn't what these tests are about, and the
    # default 30s timeout would make every test here needlessly slow.
    monkeypatch.setattr(settings, "STABILITY_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(settings, "STABILITY_TIMEOUT", 1.0)


# ---------------------------------------------------------------------------
# _do_organize_existing() -- the function actually reached when the backend
# scheduler dispatches a scheduled "organize existing files" run to a
# connected agent (via the "organize_existing" command). No direct test
# existed for it before this task -- every existing test only reaches it,
# if at all, through a monkeypatched stub -- despite it being the real,
# final step of the scheduled-organize call chain for anyone running with
# a remote agent.
# ---------------------------------------------------------------------------


def test_do_organize_existing_moves_loose_files_into_their_category_folders(tmp_path):
    watch_root = tmp_path / "watch"
    watch_root.mkdir()
    (watch_root / "report.pdf").write_text("pdf contents")
    (watch_root / "photo.jpg").write_text("jpg contents")
    conn = outbox.open_queue(tmp_path / "queue.db")

    result = commands._do_organize_existing(_OrganizeRulesClient(), watch_root, conn)

    assert result == {"scanned": 2, "organized": 2, "duplicates": 0, "errors": 0}
    assert (watch_root / "Documents" / "report.pdf").exists()
    assert (watch_root / "Images" / "photo.jpg").exists()
    assert not (watch_root / "report.pdf").exists()
    assert not (watch_root / "photo.jpg").exists()
    assert len(outbox.due_items(conn, "activity")) == 2


def test_do_organize_existing_skips_files_already_inside_a_category_subfolder(tmp_path):
    watch_root = tmp_path / "watch"
    watch_root.mkdir()
    already = watch_root / "Documents" / "already_organized.pdf"
    already.parent.mkdir(parents=True)
    already.write_text("hi")
    conn = outbox.open_queue(tmp_path / "queue.db")

    result = commands._do_organize_existing(_OrganizeRulesClient(), watch_root, conn)

    # iterdir() (not rglob) is what _do_organize_existing scans -- it never
    # descends into subfolders it (or a real download) already created, so
    # a file already sitting in a category subfolder is left completely
    # alone, not re-scanned or re-counted.
    assert result == {"scanned": 0, "organized": 0, "duplicates": 0, "errors": 0}
    assert already.exists()


def test_do_organize_existing_reports_overall_success_even_when_every_file_errors(tmp_path, monkeypatch):
    """This function's own error containment is correct and intentional:
    one bad file must not abort organizing the rest of the batch, exactly
    like watcher.py's process_download/organizer.py's process_file -- so
    _do_organize_existing() itself always returns a result with the real
    errors count, never raises on a per-file failure. (The name is kept
    from before this task's fix -- see the tests below for the actual
    success-semantics coverage, now applied one level up in _handle().)"""
    watch_root = tmp_path / "watch"
    watch_root.mkdir()
    (watch_root / "report.pdf").write_text("pdf contents")
    (watch_root / "photo.jpg").write_text("jpg contents")
    conn = outbox.open_queue(tmp_path / "queue.db")

    def _raise(*args, **kwargs):
        raise OSError("simulated disk error")

    monkeypatch.setattr(commands, "classify_file", _raise)

    result = commands._do_organize_existing(_OrganizeRulesClient(), watch_root, conn)

    assert result == {"scanned": 2, "organized": 0, "duplicates": 0, "errors": 2}
    # Both files are left untouched -- classify_file() raised before either
    # was ever moved.
    assert (watch_root / "report.pdf").exists()
    assert (watch_root / "photo.jpg").exists()
    assert outbox.due_items(conn, "activity") == []


# ---------------------------------------------------------------------------
# organize_existing success semantics -- _handle() previously reported
# success=True unconditionally for this command type regardless of the
# batch's own errors count (a confirmed, reproduced gap from the prior
# command-completion outbox audit). Fixed to success = (errors == 0),
# matching the exact contract undo/reclassify already use just above in the
# same function: success means the requested work actually happened, not
# merely that the handler returned without raising. duplicates are a
# separate, non-error outcome (see _do_organize_existing's own counters --
# a duplicate_skipped file `continue`s before its per-file except could
# ever increment errors), so they never affect success.
# ---------------------------------------------------------------------------


def _organize_completion_payload(monkeypatch, tmp_path, result):
    conn = outbox.open_queue(tmp_path / "queue.db")
    monkeypatch.setattr(commands, "_do_organize_existing", lambda client, watch_root, outbox_conn: result)
    command = {"id": 1, "type": "organize_existing", "payload": {}}
    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)
    return json.loads(outbox.due_items(conn, "command_complete")[0]["payload"])


def test_handle_reports_success_when_every_file_organizes_cleanly(tmp_path, monkeypatch):
    payload = _organize_completion_payload(
        monkeypatch, tmp_path, {"scanned": 3, "organized": 3, "duplicates": 0, "errors": 0}
    )
    assert payload["success"] is True
    assert payload["result"] == {"scanned": 3, "organized": 3, "duplicates": 0, "errors": 0}


def test_handle_reports_success_for_an_empty_batch(tmp_path, monkeypatch):
    """scanned=0, errors=0 -- nothing needed organizing, which is not a
    failure of the command."""
    payload = _organize_completion_payload(
        monkeypatch, tmp_path, {"scanned": 0, "organized": 0, "duplicates": 0, "errors": 0}
    )
    assert payload["success"] is True


def test_handle_reports_success_for_a_duplicate_only_batch(tmp_path, monkeypatch):
    """Every file was a duplicate, correctly skipped -- errors=0, so this
    is success, not failure, even though organized=0."""
    payload = _organize_completion_payload(
        monkeypatch, tmp_path, {"scanned": 2, "organized": 0, "duplicates": 2, "errors": 0}
    )
    assert payload["success"] is True


def test_handle_reports_failure_for_a_partial_failure_batch(tmp_path, monkeypatch):
    payload = _organize_completion_payload(
        monkeypatch, tmp_path, {"scanned": 10, "organized": 9, "duplicates": 0, "errors": 1}
    )
    assert payload["success"] is False
    assert payload["result"] == {"scanned": 10, "organized": 9, "duplicates": 0, "errors": 1}, (
        "the fix must only change the top-level success signal -- the result counts "
        "themselves must reach the backend completely unchanged"
    )


def test_handle_reports_failure_when_every_file_errors(tmp_path, monkeypatch):
    """Regression test for the confirmed organize_existing success-semantics
    bug: _handle() previously reported success=True unconditionally for
    organize_existing, so a batch where every single file failed to
    organize still completed as "success" -- status=done, success=true --
    from the backend's (and History's) perspective. success now reflects
    result["errors"] == 0."""
    payload = _organize_completion_payload(
        monkeypatch, tmp_path, {"scanned": 2, "organized": 0, "duplicates": 0, "errors": 2}
    )
    assert payload["success"] is False, (
        "a batch where every file failed to organize must not be reported as success"
    )


def test_handle_still_reports_failure_on_an_unexpected_pre_loop_exception(tmp_path, monkeypatch):
    """If _do_organize_existing() itself raises (rather than returning a
    result with a non-zero errors count -- e.g. watch_root disappearing
    out from under iterdir() before the per-file try/except is ever
    reached), _handle()'s own outer except Exception must still catch it,
    exactly as it already does for undo/reclassify -- unchanged by this
    task's fix, which only touches the normal-return path."""
    conn = outbox.open_queue(tmp_path / "queue.db")

    def _raise(*args, **kwargs):
        raise OSError("watch root vanished")

    monkeypatch.setattr(commands, "_do_organize_existing", _raise)
    command = {"id": 1, "type": "organize_existing", "payload": {}}

    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)

    payload = json.loads(outbox.due_items(conn, "command_complete")[0]["payload"])
    assert payload["success"] is False
    assert payload["error"] == "watch root vanished"
    assert payload["result"] == {}, "the outer except path never computed a result dict"


def test_do_undo_failed_rename_does_not_leave_a_stale_self_move_marker(tmp_path, monkeypatch):
    """mark_self_move(source) runs right before dest.rename(source) so the
    watcher ignores the move-back instead of re-organizing it. If the rename
    itself then fails (permission issue, AV lock, disk error -- anything),
    the marker must not survive: left in place, it would silently swallow
    the very next real download landing at that exact path."""
    dest = tmp_path / "Documents" / "file.txt"
    dest.parent.mkdir()
    dest.write_text("hello")
    source = tmp_path / "file.txt"

    def failing_rename(self, target):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(Path, "rename", failing_rename)

    success, error = commands._do_undo(
        {"source_path": str(source), "destination_path": str(dest)}
    )

    assert success is False
    assert error is not None
    # False here means no marker was found for `source` -- if the bug were
    # still present, this would be True (the stale entry from mark_self_move
    # still sitting in the set) and would wrongly consume/suppress the next
    # real event for this same path.
    assert _consume_self_move(source) is False


def test_handle_does_not_rerun_a_command_whose_report_is_still_queued(tmp_path, monkeypatch):
    """The backend only stops redelivering a command once it durably
    receives a completion report -- if that report is still sitting
    undelivered in the local outbox (backend briefly unreachable, or this
    cycle just hasn't flushed yet), a later poll cycle handing the same
    still-"pending" command back to _handle() must not run the handler a
    second time. A second real execution of e.g. undo would find "file
    already moved" and report failure, which -- if that second report
    reaches the backend -- would incorrectly flip an already-restored row's
    undo claim back open."""
    conn = outbox.open_queue(tmp_path / "queue.db")
    calls = []
    monkeypatch.setattr(
        commands, "_do_undo", lambda payload: (calls.append(1) or (True, None))
    )
    command = {"id": 42, "type": "undo", "payload": {}}

    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)
    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)

    assert len(calls) == 1, "the handler must only actually execute once"
    # Exactly one completion report queued too -- not a duplicate.
    assert len(outbox.due_items(conn, "command_complete")) == 1


def test_handle_does_not_rerun_a_command_after_its_completion_report_is_backed_off(tmp_path, monkeypatch):
    """The test above only covers a completion report that hasn't been
    flushed at all yet -- still due, next_attempt_at=0. This is the
    distinct, more dangerous case the has_pending_completion() backoff-
    boundary audit is about: delivery was actually ATTEMPTED, failed, and
    bump_failure() pushed next_attempt_at into the real future. If
    has_pending_completion() only asked "is a completion currently due"
    instead of "does a completion record still exist," a future
    next_attempt_at would wrongly look like "nothing pending" and let this
    exact command run a second time for real while its first outcome is
    still sitting in the outbox, undelivered."""
    conn = outbox.open_queue(tmp_path / "queue.db")
    calls = []
    monkeypatch.setattr(commands, "_do_undo", lambda payload: (calls.append(1) or (True, None)))
    command = {"id": 42, "type": "undo", "payload": {}}

    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)
    assert len(calls) == 1

    item = outbox.due_items(conn, "command_complete")[0]
    outbox.bump_failure(conn, item["id"])
    assert outbox.due_items(conn, "command_complete", now=time.time()) == [], (
        "sanity check: the item must actually be backed off (not due), or this test proves nothing"
    )
    assert outbox.has_pending_completion(conn, 42) is True

    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)

    assert len(calls) == 1, "a backed-off (not yet delivered) completion must still block re-execution"
    assert len(outbox.due_items(conn, "command_complete", now=float("inf"))) == 1


@pytest.mark.parametrize("status_code", [401, 403])
def test_handle_does_not_rerun_a_command_after_a_401_or_403_completion_failure(tmp_path, monkeypatch, status_code):
    """Directly exercises the real chain the previous outbox audit's fix
    protects, end to end through _handle() rather than through outbox.py
    in isolation: command executes -> completion queued -> 401/403 on
    delivery -> outbox.py::_is_client_error() now retries instead of
    dropping it -> has_pending_completion() must still see it -> _handle()
    must not run the same command a second time during that backoff
    window, even once the backend's still-"pending" copy of it is handed
    back to this agent by a later poll cycle."""
    conn = outbox.open_queue(tmp_path / "queue.db")
    calls = []
    monkeypatch.setattr(commands, "_do_undo", lambda payload: (calls.append(1) or (True, None)))
    command = {"id": 42, "type": "undo", "payload": {}}

    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)
    assert len(calls) == 1

    class _FailingClient:
        def complete_command(self, **kwargs):
            raise _http_error(status_code)

    outbox.flush_outbox(_FailingClient(), conn)
    assert outbox.has_pending_completion(conn, 42) is True

    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)

    assert len(calls) == 1, f"a {status_code} completion failure must not let the command re-execute"


def test_handle_does_not_rerun_a_command_after_a_connection_failure_completion_report(tmp_path, monkeypatch):
    """Same boundary as the 401/403 test above, for the other realistic
    cause of a backed-off completion: the backend is simply unreachable.
    Confirms auth failures and connection failures share the same
    protection against duplicate execution."""
    conn = outbox.open_queue(tmp_path / "queue.db")
    calls = []
    monkeypatch.setattr(commands, "_do_undo", lambda payload: (calls.append(1) or (True, None)))
    command = {"id": 42, "type": "undo", "payload": {}}

    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)
    assert len(calls) == 1

    class _OfflineClient:
        def complete_command(self, **kwargs):
            raise requests.exceptions.ConnectionError("offline")

    outbox.flush_outbox(_OfflineClient(), conn)
    assert outbox.has_pending_completion(conn, 42) is True

    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)

    assert len(calls) == 1, "a connection-failure completion report must not let the command re-execute"


def test_handle_can_rerun_a_command_after_its_completion_is_actually_delivered(tmp_path, monkeypatch):
    """The other half of the boundary: has_pending_completion() must stop
    blocking once the completion has genuinely been delivered and removed
    -- confirming the guard tracks "does a completion record still exist,"
    not some other condition that could get permanently stuck true. (In
    real operation this specific sequence -- the SAME command_id handed to
    _handle() again after its completion already succeeded -- shouldn't
    happen, since the backend stops returning a command from
    GET /api/agent/commands once its status is no longer "pending"; this
    test isolates the outbox-guard half of that contract on its own.)"""
    conn = outbox.open_queue(tmp_path / "queue.db")
    calls = []
    monkeypatch.setattr(commands, "_do_undo", lambda payload: (calls.append(1) or (True, None)))
    command = {"id": 42, "type": "undo", "payload": {}}

    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)
    assert len(calls) == 1

    class _SucceedingClient:
        def complete_command(self, **kwargs):
            pass

    outbox.flush_outbox(_SucceedingClient(), conn)
    assert outbox.has_pending_completion(conn, 42) is False

    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)

    assert len(calls) == 2, "once delivered, the guard must no longer block a later legitimate call"


# ---------------------------------------------------------------------------
# poll_forever()'s self-update integration -- this is the actual real-world
# home of os._exit(0) (it is NOT inside updater.py itself, despite the
# module docstring's high-level summary; see the self-update audit for the
# full trace). These tests never let a real os._exit() run: it's monkey-
# patched to raise a sentinel exception instead, which also doubles as the
# only safe way to stop poll_forever()'s otherwise-infinite loop.
# ---------------------------------------------------------------------------


class _StopLoop(BaseException):
    """Raised by a patched os._exit()/time.sleep() to unwind out of
    poll_forever()'s `while True:` after exactly one iteration -- never
    calling the real os._exit(), which would kill the pytest process.
    Deliberately subclasses BaseException, not Exception: poll_forever()'s
    own `except Exception:` handler would otherwise silently swallow this
    sentinel too, logging it and looping forever instead of unwinding."""


class _PollClient:
    """Minimal client stub for poll_forever(): with an empty outbox and no
    pending files, flush_outbox()/retry_pending_files() never call any
    client method, so get_commands() (kept empty) is the only one poll_
    forever() itself actually needs."""

    def get_commands(self):
        return []


def test_poll_forever_terminates_the_process_after_a_successful_update_launch(tmp_path, monkeypatch):
    """The real integration this whole audit is about: a successful
    check_for_update()+download_and_apply() must shut the runtime down
    (on_before_update_exit) *before* calling os._exit(0), in that order."""
    monkeypatch.setattr(commands.updater, "check_for_update", lambda client: {"version": "9.9.9"})
    monkeypatch.setattr(commands.updater, "download_and_apply", lambda client, manifest: True)
    monkeypatch.setattr(commands, "notify", lambda *a, **k: None)
    events = []

    def _on_before_update_exit():
        events.append("shutdown")

    def _fake_exit(code):
        events.append(("exit", code))
        raise _StopLoop

    monkeypatch.setattr(commands.os, "_exit", _fake_exit)
    conn = outbox.open_queue(tmp_path / "queue.db")

    with pytest.raises(_StopLoop):
        commands.poll_forever(_PollClient(), tmp_path, conn, on_before_update_exit=_on_before_update_exit)

    assert events == ["shutdown", ("exit", 0)], "the runtime must be shut down before the process exits"


def test_poll_forever_does_not_terminate_when_no_update_is_available(tmp_path, monkeypatch):
    monkeypatch.setattr(commands.updater, "check_for_update", lambda client: None)
    exit_calls = []
    monkeypatch.setattr(commands.os, "_exit", lambda code: exit_calls.append(code))

    def _stop_after_one_iteration(seconds):
        raise _StopLoop

    monkeypatch.setattr(commands.time, "sleep", _stop_after_one_iteration)
    conn = outbox.open_queue(tmp_path / "queue.db")

    with pytest.raises(_StopLoop):
        commands.poll_forever(_PollClient(), tmp_path, conn)

    assert exit_calls == []


def test_poll_forever_survives_an_update_apply_failure_without_terminating(tmp_path, monkeypatch):
    """download_and_apply() has no try/except of its own around the write/
    launch boundary (see test_updater.py) -- this is the safety net that
    actually matters: poll_forever()'s own broad `except Exception:` must
    catch a raised failure there, never reach os._exit, and let the loop
    continue rather than crashing the polling thread."""
    monkeypatch.setattr(commands.updater, "check_for_update", lambda client: {"version": "9.9.9"})

    def _raise(client, manifest):
        raise OSError("simulated disk-full while writing the installer")

    monkeypatch.setattr(commands.updater, "download_and_apply", _raise)
    exit_calls = []
    monkeypatch.setattr(commands.os, "_exit", lambda code: exit_calls.append(code))

    def _stop_after_one_iteration(seconds):
        raise _StopLoop

    monkeypatch.setattr(commands.time, "sleep", _stop_after_one_iteration)
    conn = outbox.open_queue(tmp_path / "queue.db")

    with pytest.raises(_StopLoop):
        commands.poll_forever(_PollClient(), tmp_path, conn)

    assert exit_calls == [], "an apply failure must never reach process termination"


def test_poll_forever_does_not_recheck_for_an_update_immediately_after_a_failed_attempt(tmp_path, monkeypatch):
    """next_update_check is advanced by UPDATE_CHECK_INTERVAL_SECONDS (6
    hours) BEFORE check_for_update()/download_and_apply() are even
    called -- so every outcome (success, download failure, checksum
    mismatch, write failure, launch failure) defers the next attempt by
    the same fixed interval, not just a successful one. Confirms a failed
    update does not cause an immediate retry on the very next poll cycle
    a few seconds later -- consistent with the deliberate "avoid hitting
    the backend every 5 seconds" design already documented on
    UPDATE_CHECK_INTERVAL_SECONDS itself."""
    check_calls = []

    def _fake_check(client):
        check_calls.append(1)
        return {"version": "9.9.9"}

    def _fake_apply(client, manifest):
        raise OSError("simulated disk-full while writing the installer")

    monkeypatch.setattr(commands.updater, "check_for_update", _fake_check)
    monkeypatch.setattr(commands.updater, "download_and_apply", _fake_apply)
    conn = outbox.open_queue(tmp_path / "queue.db")

    sleeps = _run_poll_forever_capturing_sleeps(_PollClient(), tmp_path, conn, iterations=2)

    assert len(sleeps) == 2
    assert len(check_calls) == 1, (
        "a failed update attempt must not be immediately retried on the very next poll "
        "cycle -- next_update_check must already be set ~6 hours in the future"
    )


# ---------------------------------------------------------------------------
# poll_forever()'s watch_root -- a real, confirmed concurrency bug found
# during the Reconfigure concurrency audit. get_handler (already existing)
# is re-called every iteration specifically so a Reconfigure that swaps in
# a brand new handler keeps working (see poll_forever's own comment on
# get_handler). watch_root itself never got the same treatment: it's a
# plain parameter captured ONCE when the background thread starts
# (agent/main.py passes self.watch_root positionally at AgentRuntime.
# __init__ time), so a watch-folder Reconfigure later in the same process's
# life left every reclassify/organize_existing command computed against
# the OLD folder for good, even though the handler/observer had already
# correctly swapped to the new one.
# ---------------------------------------------------------------------------


def test_poll_forever_reclassify_uses_the_current_watch_root_after_a_reconfigure(tmp_path, monkeypatch):
    old_root = tmp_path / "old_watch"
    new_root = tmp_path / "new_watch"
    old_root.mkdir()
    new_root.mkdir()

    command = {"id": 1, "type": "reclassify", "payload": {"source_path": "irrelevant", "category": "Documents"}}
    seen_watch_roots = []

    def _fake_reclassify(client, watch_root, payload):
        seen_watch_roots.append(watch_root)
        return True, None, {}

    monkeypatch.setattr(commands, "_do_reclassify", _fake_reclassify)
    monkeypatch.setattr(commands.time, "sleep", lambda seconds: None)

    class _Client:
        def __init__(self):
            self._sent = False

        def get_commands(self):
            if self._sent:
                raise _StopLoop
            self._sent = True
            return [command]

        def get_latest_version(self):
            raise requests.exceptions.ConnectionError("offline")

        def complete_command(self, **kwargs):
            pass

    conn = outbox.open_queue(tmp_path / "queue.db")
    # Simulates AgentRuntime.watch_root right after apply_config() has
    # already swapped it to the new folder -- exactly what main.py's
    # get_watch_root=lambda: self.watch_root provides for real.
    current = {"value": new_root}

    with pytest.raises(_StopLoop):
        commands.poll_forever(_Client(), old_root, conn, get_watch_root=lambda: current["value"])

    assert seen_watch_roots == [new_root], (
        "the poll thread must resolve the CURRENT watch root on every iteration "
        "(like it already does for the handler via get_handler), not the one it "
        "happened to be started with"
    )


# ---------------------------------------------------------------------------
# poll_forever()'s handling of a malformed-but-valid get_commands() response
# -- HTTP 200, valid JSON, wrong shape (missing "id"/"type", or not even a
# dict) is entirely distinct from a network/HTTP failure: get_commands()
# itself returns normally, and the exception (KeyError/TypeError) comes
# from _handle() reading a field the response doesn't actually have. The
# real backend route (agent_routes.py::get_pending_commands) always builds
# AgentCommandOut(id=..., type=..., payload=...) from real fields, so this
# can't happen against the current, unmodified backend -- but agent/backend
# version skew, or a future backend change, are realistic enough that this
# path is worth tracing rather than assuming "can't happen."
# ---------------------------------------------------------------------------


def _run_poll_forever_capturing_sleeps(client, watch_root, conn, iterations):
    """Runs poll_forever() for exactly `iterations` cycles, returning the
    list of backoff values it passed to time.sleep() -- a controlled stop
    condition (not an arbitrary sleep), matching the existing _StopLoop
    pattern used throughout this file to safely terminate poll_forever()'s
    otherwise-infinite loop without ever letting a real time.sleep() run."""
    sleeps = []

    def _record_and_maybe_stop(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= iterations:
            raise _StopLoop

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(commands.time, "sleep", _record_and_maybe_stop)
        with pytest.raises(_StopLoop):
            commands.poll_forever(client, watch_root, conn)
    return sleeps


@pytest.mark.parametrize(
    "malformed_response",
    [
        pytest.param({"commands": []}, id="dict_with_wrong_key"),
        pytest.param(["not-a-command"], id="list_of_non_dict_items"),
        pytest.param([{"id": 1}], id="missing_type"),
        pytest.param([{"type": "undo"}], id="missing_id"),
    ],
)
def test_poll_forever_backs_off_after_a_malformed_get_commands_response(tmp_path, malformed_response):
    """Regression test for a real, confirmed bug: poll_forever()'s generic
    `except Exception:` branch (distinct from its `except requests.
    exceptions.RequestException:` branch just above it, which correctly
    sets healthy=False) logged the exception but never touched `healthy`
    -- so a poll cycle that failed because get_commands() returned a
    VALID-BUT-WRONG-SHAPED response was treated exactly like a fully
    healthy cycle: backoff reset to POLL_INTERVAL_SECONDS (5s) instead of
    growing. Since a malformed command can never be marked "done" (no
    completion is ever queued for it -- _handle() raises before reaching
    enqueue_command_complete()), the exact same response is returned again
    every single poll -- so this reset the agent into hammering the
    backend and re-raising/re-logging the same exception every 5 seconds
    forever, instead of backing off like every other kind of poll-cycle
    failure already does."""
    conn = outbox.open_queue(tmp_path / "queue.db")

    class _MalformedClient:
        def get_commands(self):
            return malformed_response

    sleeps = _run_poll_forever_capturing_sleeps(_MalformedClient(), tmp_path, conn, iterations=3)

    assert sleeps == [10, 20, 40], (
        "a poll cycle that fails on a malformed command response must back off "
        "exponentially exactly like any other failed cycle -- not reset to "
        f"full-speed polling every time (got {sleeps})"
    )


def test_poll_forever_treats_an_empty_dict_response_as_zero_commands_and_stays_healthy(tmp_path):
    """{} is not a realistic backend response (the real route always
    returns a list, even when empty), but Python's own `for x in {}:`
    semantics make it completely benign regardless: an empty dict iterates
    zero times, so zero commands are processed, nothing raises, and the
    cycle correctly stays healthy -- included here to draw an explicit
    line between "malformed shapes that raise" (tested above, and which
    must back off) and "malformed shapes that just do nothing" (this one,
    which correctly does not)."""
    conn = outbox.open_queue(tmp_path / "queue.db")

    class _EmptyDictClient:
        def get_commands(self):
            return {}

        def get_latest_version(self):
            # check_for_update() catches RequestException internally and
            # returns None -- this keeps the update-check step (which runs
            # right after the command loop, since nothing here raises)
            # from needing its own client method beyond this.
            raise requests.exceptions.ConnectionError("offline")

    sleeps = _run_poll_forever_capturing_sleeps(_EmptyDictClient(), tmp_path, conn, iterations=1)

    assert sleeps == [commands.POLL_INTERVAL_SECONDS]


def test_poll_forever_stays_healthy_for_an_unrecognized_but_well_formed_command_type(tmp_path):
    """Distinct from the malformed-shape cases above: {"id", "type",
    "payload"} are all present here, just an unrecognized `type` value
    (e.g. an older agent talking to a newer backend that introduced a
    command type this build doesn't know about yet). _handle() already
    handles this safely -- logs a warning and returns, no exception at
    all -- so this must NOT back off, unlike the genuinely malformed
    shapes above."""
    conn = outbox.open_queue(tmp_path / "queue.db")

    class _UnknownTypeClient:
        def get_commands(self):
            return [{"id": 1, "type": "some_future_command_type", "payload": {}}]

        def complete_command(self, **kwargs):
            pass

        def get_latest_version(self):
            raise requests.exceptions.ConnectionError("offline")

    sleeps = _run_poll_forever_capturing_sleeps(_UnknownTypeClient(), tmp_path, conn, iterations=1)

    assert sleeps == [commands.POLL_INTERVAL_SECONDS]


def test_poll_forever_runs_commands_listed_before_a_malformed_one_but_not_those_listed_after_it(
    tmp_path, monkeypatch
):
    """There is no per-command try/except in poll_forever()'s `for command
    in client.get_commands(): _handle(...)` loop -- an exception from one
    command aborts the rest of that same for loop entirely. This documents
    (does not change -- out of scope for this task, which is about
    health/backoff, not command isolation) the resulting behavior: a
    command listed BEFORE the malformed one in the same response still
    executes; one listed AFTER it does not run this cycle."""
    conn = outbox.open_queue(tmp_path / "queue.db")
    handled = []
    monkeypatch.setattr(commands, "_do_undo", lambda payload: (handled.append(payload["marker"]) or (True, None)))

    good_first = {"id": 1, "type": "undo", "payload": {"marker": "first"}}
    malformed = {"id": 2}  # missing "type"
    good_later = {"id": 3, "type": "undo", "payload": {"marker": "later"}}

    class _Client:
        def get_commands(self):
            return [good_first, malformed, good_later]

    _run_poll_forever_capturing_sleeps(_Client(), tmp_path, conn, iterations=1)

    assert handled == ["first"], (
        "the command listed before the malformed one must still execute, but the one "
        "listed after it must not run this cycle -- the malformed command aborts the "
        "rest of the same for loop rather than being skipped over"
    )


@pytest.mark.parametrize(
    "malformed_command",
    [
        pytest.param("not-a-command", id="not_a_dict"),
        pytest.param({"id": 1}, id="missing_type"),
        pytest.param({"type": "undo"}, id="missing_id"),
    ],
)
def test_handle_raises_on_a_structurally_malformed_command_instead_of_silently_misbehaving(
    tmp_path, malformed_command
):
    """_handle() itself has no schema validation before touching
    command["id"] / command["type"] -- confirms each of these realistic
    valid-JSON-wrong-shape cases raises a real Python exception (surfaced
    to poll_forever()'s own exception handling, tested above) rather than
    silently doing nothing or misbehaving in some quieter, harder-to-
    diagnose way."""
    conn = outbox.open_queue(tmp_path / "queue.db")
    with pytest.raises((KeyError, TypeError)):
        commands._handle(client=None, watch_root=tmp_path, command=malformed_command, outbox_conn=conn)


# ---------------------------------------------------------------------------
# flush_outbox()'s health signal -- outbox.flush_outbox(client, outbox_conn)
# is called here with its return value entirely discarded, unlike
# retry_pending_files() one line below it, whose return value IS checked
# (`if not retry_pending_files(...): healthy = False`). A connection-level
# failure delivering an "activity" or "command_complete" report is the same
# kind of signal retry_pending_files() already treats as "this cycle didn't
# fully succeed, back off" -- POST /api/agent/activity, POST /api/agent/
# commands/{id}/complete, GET /api/agent/rules (retry_pending_files' own
# network exposure, via process_download), and GET /api/agent/commands are
# four genuinely independent routes/code paths (confirmed by reading each
# one), so one failing while the others succeed is realistic, not
# contrived -- e.g. a transient error specific to inserting into
# activity_log/agent_commands while everything else on the backend is fine.
# ---------------------------------------------------------------------------


def test_poll_forever_backs_off_when_flush_outbox_has_a_retryable_activity_delivery_failure(tmp_path):
    """Regression test for a real, confirmed bug: a poll cycle where ONLY
    the activity-report endpoint fails (get_commands() and an empty
    retry_pending_files() both succeed) was incorrectly treated as fully
    healthy -- backoff reset to POLL_INTERVAL_SECONDS instead of growing,
    because flush_outbox()'s own success/failure never reached
    poll_forever()'s `healthy` variable."""
    conn = outbox.open_queue(tmp_path / "queue.db")
    outbox.enqueue_activity(conn, client_ref="a")

    class _ActivityEndpointDownClient:
        def report_activity(self, **kwargs):
            raise requests.exceptions.ConnectionError("activity endpoint down")

        def get_commands(self):
            return []

        def get_latest_version(self):
            # check_for_update() catches RequestException internally and
            # returns None -- isolates this test to ONLY the activity
            # delivery failure below, not an unrelated missing-stub error
            # from the separate update-check step later in the same cycle.
            raise requests.exceptions.ConnectionError("offline")

    sleeps = _run_poll_forever_capturing_sleeps(_ActivityEndpointDownClient(), tmp_path, conn, iterations=1)

    assert sleeps == [10], (
        "a retryable flush_outbox() delivery failure must back off the poll cycle "
        f"the same way retry_pending_files()'s own failures already do (got {sleeps})"
    )
    assert len(outbox.due_items(conn, "activity", now=float("inf"))) == 1, "the item must remain queued"


def test_poll_forever_backs_off_when_flush_outbox_has_a_retryable_command_complete_delivery_failure(
    tmp_path, monkeypatch
):
    """Same bug, for the command_complete kind specifically -- confirms the
    fix isn't accidentally scoped to only the activity kind (flush_outbox()
    flushes both kinds through the exact same _flush_kind() codepath,
    sharing the same previously-discarded return value)."""
    conn = outbox.open_queue(tmp_path / "queue.db")
    monkeypatch.setattr(commands, "_do_undo", lambda payload: (True, None))
    commands._handle(
        client=None, watch_root=tmp_path, command={"id": 1, "type": "undo", "payload": {}}, outbox_conn=conn
    )
    assert len(outbox.due_items(conn, "command_complete")) == 1

    class _CompleteEndpointDownClient:
        def complete_command(self, **kwargs):
            raise requests.exceptions.ConnectionError("complete endpoint down")

        def get_commands(self):
            return []

        def get_latest_version(self):
            raise requests.exceptions.ConnectionError("offline")

    sleeps = _run_poll_forever_capturing_sleeps(_CompleteEndpointDownClient(), tmp_path, conn, iterations=1)

    assert sleeps == [10], f"expected backoff after a retryable command_complete delivery failure (got {sleeps})"


def test_flush_outbox_health_fix_does_not_cause_command_re_execution_or_completion_loss(tmp_path, monkeypatch):
    """Confirms the health/backoff fix is exactly what it claims to be --
    a change to poll_forever()'s SLEEP timing only. It must not touch
    has_pending_completion(), must not re-execute the command, and must
    not alter the completion payload still safely queued and waiting for
    its own backoff to elapse -- preserving the established "file
    operation success != backend completion-report success" separation
    from the earlier command-completion audits, even in a cycle where the
    backend also happens to redeliver the still-"pending" command."""
    conn = outbox.open_queue(tmp_path / "queue.db")
    calls = []
    monkeypatch.setattr(commands, "_do_undo", lambda payload: (calls.append(1) or (True, None)))
    command = {"id": 42, "type": "undo", "payload": {}}
    commands._handle(client=None, watch_root=tmp_path, command=command, outbox_conn=conn)
    assert len(calls) == 1

    class _CompleteEndpointDownClient:
        def complete_command(self, **kwargs):
            raise requests.exceptions.ConnectionError("offline")

        def get_commands(self):
            # The backend still thinks this command is "pending" (its
            # completion report hasn't landed) and redelivers it in the
            # very same cycle the delivery attempt above just failed in.
            return [command]

        def get_latest_version(self):
            raise requests.exceptions.ConnectionError("offline")

    _run_poll_forever_capturing_sleeps(_CompleteEndpointDownClient(), tmp_path, conn, iterations=1)

    assert len(calls) == 1, "the health/backoff fix must not cause the command to be re-executed"
    assert outbox.has_pending_completion(conn, 42) is True
    payload = json.loads(outbox.due_items(conn, "command_complete", now=float("inf"))[0]["payload"])
    assert payload == {"command_id": 42, "success": True, "error": None, "result": {}}, (
        "the queued completion payload must reach the backend unchanged once delivery "
        "eventually succeeds -- the health/backoff timing change must not touch it"
    )


def test_retry_pending_files_backs_off_instead_of_permanently_dropping_the_item_when_the_cache_is_corrupted(
    tmp_path, monkeypatch
):
    """Regression test for a real, confirmed bug, reproduced against the
    unfixed code before this fix: rules_cache.get_rules() used to let a
    corrupted cache raise a raw json.JSONDecodeError instead of
    RequestException. retry_pending_files() only backs off (bump_failure,
    keep the item queued) for RequestException specifically -- anything
    else falls into its broader except-Exception branch, which logs and
    permanently *deletes* the queued item instead. That meant a corrupted
    local rules cache, combined with the backend being unreachable, caused
    every pending file to be silently, permanently dropped -- never
    organized, with no trace left to retry later -- even though the actual
    file and the backend outage were both completely fine on their own."""
    monkeypatch.setattr(rules_cache, "CACHE_PATH", tmp_path / "rules_cache.json")
    rules_cache.CACHE_PATH.write_text("{not valid json")

    watch_root = tmp_path / "watch"
    watch_root.mkdir()
    pending_file = watch_root / "document.pdf"
    pending_file.write_text("hello")
    conn = outbox.open_queue(tmp_path / "queue.db")
    outbox.enqueue_pending_file(conn, pending_file)

    class _OfflineClient:
        def get_rules(self):
            raise requests.exceptions.ConnectionError("offline")

    result = commands.retry_pending_files(_OfflineClient(), watch_root, conn)

    assert result is False, "an unreachable backend must be reported so poll_forever backs off"
    assert len(outbox.due_items(conn, "pending_file", now=float("inf"))) == 1, (
        "the pending file must still be queued for a later retry, not silently dropped"
    )
    assert pending_file.exists(), "the file itself must be untouched"
