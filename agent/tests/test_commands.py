from pathlib import Path

import pytest
import requests

from agent import commands, outbox, rules_cache
from agent.watcher import _consume_self_move
from config.settings import settings

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
    """Regression-documenting test for a real, confirmed observability gap
    (not a correctness bug -- deliberately not "fixed" by changing this
    function's own error containment, which is correct and intentional:
    one bad file must not abort organizing the rest of the batch, exactly
    like watcher.py's process_download/organizer.py's process_file).

    The gap is one level up, in _handle() (see commands.py): it reports
    success=True to the backend unconditionally for organize_existing
    commands, regardless of this function's own `errors` count -- so a
    scheduled run where EVERY file fails to organize still completes as
    "success" from the backend's perspective. This test locks in exactly
    what _do_organize_existing itself reports (errors counted, nothing
    silently swallowed at this layer) so that fact is pinned down and
    traceable to the _handle()-level gap, not confused with this
    function's own (correct) per-file error containment."""
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

    # _handle() -- the caller that actually reports this command's outcome
    # to the backend -- receives this exact result but ignores its errors
    # count entirely.
    command = {"id": 1, "type": "organize_existing", "payload": {}}
    commands._handle(_OrganizeRulesClient(), watch_root, command, conn)
    completion = outbox.due_items(conn, "command_complete")[0]
    import json as _json

    payload = _json.loads(completion["payload"])
    assert payload["success"] is True, (
        "confirmed gap: _handle() reports success=True for organize_existing "
        "even when every single file in the batch errored"
    )
    assert payload["result"]["errors"] == 2, "the real error count IS present in the payload, just not surfaced as success=False"


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
