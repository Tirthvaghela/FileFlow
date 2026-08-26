import json
import threading

import pytest
import requests

from agent import outbox, rules_cache
from agent.watcher import AgentDownloadHandler, process_download
from config.settings import settings


def _handler():
    return AgentDownloadHandler(client=None, watch_root=None, outbox_conn=None)


def test_not_paused_by_default():
    h = _handler()
    assert h.paused is False


def test_manual_pause_alone_pauses():
    h = _handler()
    h.manually_paused = True
    assert h.paused is True


def test_remote_disable_alone_pauses():
    h = _handler()
    h.remote_monitoring_disabled = True
    assert h.paused is True


def test_both_must_clear_to_resume():
    """The exact scenario the split exists for: pausing from the tray
    while the website's toggle still has monitoring on must not resume
    just because the website says so, and vice versa."""
    h = _handler()
    h.manually_paused = True
    h.remote_monitoring_disabled = True

    h.remote_monitoring_disabled = False
    assert h.paused is True, "Still manually paused -- should stay paused."

    h.manually_paused = False
    assert h.paused is False, "Both cleared -- should resume."


# ---------------------------------------------------------------------------
# process_download() -- the file-moving pipeline itself. These turn the
# manual real-world verification already performed for this function into
# permanent regressions: a real watch folder (tmp_path), a real outbox
# (SQLite), a real, isolated rules cache -- only the network boundary
# (AgentClient.get_rules()) is faked, exactly as instructed.
# ---------------------------------------------------------------------------

RULES = {
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


class _RulesClient:
    """Stand-in for AgentClient. process_download only ever calls
    .get_rules() on its client (via rules_cache.get_rules) -- that's the
    only method a fake needs. online=False raises the same exception type
    `requests` itself would raise for an unreachable backend."""

    def __init__(self, rules=None, online=True):
        self.rules = rules if rules is not None else RULES
        self.online = online

    def get_rules(self):
        if not self.online:
            raise requests.exceptions.ConnectionError("simulated offline")
        return self.rules


@pytest.fixture()
def watch_root(tmp_path, monkeypatch):
    root = tmp_path / "watch"
    root.mkdir()
    # Real stability-poll loop, just fast -- it isn't what these tests are
    # about, and the default 30s timeout would make every test here slow.
    monkeypatch.setattr(settings, "STABILITY_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(settings, "STABILITY_TIMEOUT", 1.0)
    return root


@pytest.fixture()
def outbox_conn(tmp_path):
    conn = outbox.open_queue(tmp_path / "outbox.db")
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def isolated_rules_cache(tmp_path, monkeypatch):
    # The real cache file lives next to the rules_cache module -- shared
    # process-wide. Isolating it per test is what makes the "offline, no
    # cache yet" tests below actually mean what they say, instead of
    # silently picking up a cache file some other test (or a previous
    # manual run) already left behind.
    monkeypatch.setattr(rules_cache, "CACHE_PATH", tmp_path / "rules_cache.json")


def test_normal_file_drop_is_classified_and_moved(watch_root, outbox_conn):
    source = watch_root / "document.pdf"
    source.write_text("pdf contents")
    unrelated = watch_root / "untouched.txt"
    unrelated.write_text("leave me alone")

    process_download(_RulesClient(), watch_root, outbox_conn, source)

    dest = watch_root / "Documents" / "document.pdf"
    assert dest.exists()
    assert dest.read_text() == "pdf contents"
    assert not source.exists()
    # Nothing else in the watch root should have been touched.
    assert unrelated.exists()
    assert unrelated.read_text() == "leave me alone"


def test_identical_duplicate_is_skipped_and_source_left_in_place(watch_root, outbox_conn):
    dest_folder = watch_root / "Documents"
    dest_folder.mkdir()
    (dest_folder / "document.pdf").write_text("same content")
    source = watch_root / "document.pdf"
    source.write_text("same content")

    process_download(_RulesClient(), watch_root, outbox_conn, source)

    assert (dest_folder / "document.pdf").read_text() == "same content"
    assert source.exists(), "duplicate_skipped means the source is left exactly where it landed"
    assert source.read_text() == "same content"
    assert not list(dest_folder.glob("document (*).pdf")), "no renamed copy should exist"

    rows = outbox.due_items(outbox_conn, "activity")
    assert len(rows) == 1
    payload = json.loads(rows[0]["payload"])
    assert payload["action"] == "duplicate_skipped"
    assert payload["destination_path"] is None


def test_different_content_duplicate_is_renamed_with_a_counter_suffix(watch_root, outbox_conn):
    dest_folder = watch_root / "Documents"
    dest_folder.mkdir()
    (dest_folder / "document.pdf").write_text("original")
    source = watch_root / "document.pdf"
    source.write_text("different content")

    process_download(_RulesClient(), watch_root, outbox_conn, source)

    assert (dest_folder / "document.pdf").read_text() == "original", "original must not be overwritten"
    renamed = dest_folder / "document (1).pdf"
    assert renamed.exists()
    assert renamed.read_text() == "different content"
    assert not source.exists()


def test_duplicate_handling_skip_mode_ignores_content_and_leaves_source_in_place(watch_root, outbox_conn):
    """Distinct from the default "rename" mode's duplicate handling above:
    "skip" mode never even compares content -- any existing file at that
    destination name is reason enough to skip, whether or not the bytes
    actually match."""
    rules = {**RULES, "duplicate_handling": "skip"}
    dest_folder = watch_root / "Documents"
    dest_folder.mkdir()
    (dest_folder / "document.pdf").write_text("original")
    source = watch_root / "document.pdf"
    source.write_text("totally different content")

    process_download(_RulesClient(rules), watch_root, outbox_conn, source)

    assert (dest_folder / "document.pdf").read_text() == "original"
    assert source.exists()
    assert not (dest_folder / "document (1).pdf").exists()


def test_duplicate_handling_replace_mode_overwrites_the_destination(watch_root, outbox_conn):
    rules = {**RULES, "duplicate_handling": "replace"}
    dest_folder = watch_root / "Documents"
    dest_folder.mkdir()
    (dest_folder / "document.pdf").write_text("stale content")
    source = watch_root / "document.pdf"
    source.write_text("fresh content")

    process_download(_RulesClient(rules), watch_root, outbox_conn, source)

    dest = dest_folder / "document.pdf"
    assert dest.exists()
    assert dest.read_text() == "fresh content"
    assert not source.exists()


def test_offline_backend_with_no_cache_leaves_the_file_untouched(watch_root, outbox_conn):
    source = watch_root / "document.pdf"
    source.write_text("pdf contents")

    with pytest.raises(requests.exceptions.RequestException):
        process_download(_RulesClient(online=False), watch_root, outbox_conn, source)

    assert source.exists(), "no classification could happen -- must not move a half-processed file"
    assert source.read_text() == "pdf contents"
    assert not (watch_root / "Documents").exists(), "nothing should have been organized at all"
    assert outbox.due_items(outbox_conn, "activity") == []


def test_offline_backend_with_cached_rules_still_organizes_the_file(watch_root, outbox_conn):
    """Protects the documented stale-while-revalidate behavior: rules
    fetched once while online remain usable for classification even once
    the backend goes away."""
    rules_cache.get_rules(_RulesClient())  # populates the cache for real

    source = watch_root / "document.pdf"
    source.write_text("pdf contents")

    process_download(_RulesClient(online=False), watch_root, outbox_conn, source)

    dest = watch_root / "Documents" / "document.pdf"
    assert dest.exists()
    assert dest.read_text() == "pdf contents"
    assert not source.exists()


def test_missing_source_file_is_a_safe_noop(watch_root, outbox_conn):
    """A file that vanished (moved/deleted elsewhere) between being
    detected and being processed must not raise or half-process anything."""
    ghost = watch_root / "already_gone.pdf"

    process_download(_RulesClient(), watch_root, outbox_conn, ghost)

    assert outbox.due_items(outbox_conn, "activity") == []
    assert not (watch_root / "Documents").exists()


def test_successful_move_queues_exactly_one_correctly_populated_activity(watch_root, outbox_conn):
    source = watch_root / "document.pdf"
    source.write_text("pdf contents")

    process_download(_RulesClient(), watch_root, outbox_conn, source)

    rows = outbox.due_items(outbox_conn, "activity")
    assert len(rows) == 1
    payload = json.loads(rows[0]["payload"])
    assert payload["original_filename"] == "document.pdf"
    assert payload["final_filename"] == "document.pdf"
    assert payload["category"] == "Documents"
    assert payload["action"] == "moved"
    assert payload["destination_path"] == str(watch_root / "Documents" / "document.pdf")
    assert payload["client_ref"], "needed for the backend to dedupe a retried delivery"


# ---------------------------------------------------------------------------
# Real multi-file-drop concurrency -- AgentDownloadHandler._handle() spawns
# a brand new daemon thread per filesystem event (confirmed by direct code
# read), so two files landing at the same moment genuinely enter
# rules_cache.get_rules() concurrently, not just theoretically. This drives
# that real thread-spawning path (not a reimplementation of it) and forces
# genuine overlap with a threading.Barrier inside the fake client's
# get_rules(), rather than hoping two _handle() calls happen to race.
# ---------------------------------------------------------------------------


def test_two_simultaneous_file_events_spawn_real_concurrent_threads_that_both_organize_correctly(
    watch_root, outbox_conn
):
    barrier = threading.Barrier(2, timeout=5)

    class _SynchronizedRulesClient:
        def get_rules(self):
            barrier.wait()  # both threads must arrive here together
            return RULES

    handler = AgentDownloadHandler(client=_SynchronizedRulesClient(), watch_root=watch_root, outbox_conn=outbox_conn)

    file_a = watch_root / "a.pdf"
    file_a.write_text("A contents")
    file_b = watch_root / "b.jpg"
    file_b.write_text("B contents")

    before = set(threading.enumerate())
    handler._handle(file_a)
    handler._handle(file_b)
    spawned = [t for t in threading.enumerate() if t not in before]
    assert len(spawned) == 2, "_handle() must spawn one new thread per file event"
    for t in spawned:
        t.join(timeout=5)
    assert not any(t.is_alive() for t in spawned), "a processing thread never completed -- likely deadlocked"

    assert (watch_root / "Documents" / "a.pdf").exists()
    assert (watch_root / "Images" / "b.jpg").exists()
    assert not file_a.exists()
    assert not file_b.exists()

    cache_content = json.loads(rules_cache.CACHE_PATH.read_text(encoding="utf-8"))
    assert cache_content == RULES, "the cache left behind by two concurrent successful fetches must be valid"
