import json
import pathlib
import threading
import time

import pytest
import requests

from agent import rules_cache


@pytest.fixture(autouse=True)
def isolated_cache_path(tmp_path, monkeypatch):
    monkeypatch.setattr(rules_cache, "CACHE_PATH", tmp_path / "rules_cache.json")
    return rules_cache.CACHE_PATH


class _OkClient:
    def __init__(self, rules):
        self._rules = rules

    def get_rules(self):
        return self._rules


class _OfflineClient:
    def get_rules(self):
        raise requests.exceptions.ConnectionError("offline")


def test_live_fetch_caches_to_disk(isolated_cache_path):
    rules = {"categories": {"Documents": [".pdf"]}}
    result = rules_cache.get_rules(_OkClient(rules))
    assert result == rules
    assert json.loads(isolated_cache_path.read_text()) == rules


def test_falls_back_to_cache_on_connection_failure(isolated_cache_path):
    cached = {"categories": {"Images": [".png"]}}
    isolated_cache_path.write_text(json.dumps(cached))
    result = rules_cache.get_rules(_OfflineClient())
    assert result == cached


def test_no_cache_and_failure_reraises(isolated_cache_path):
    assert not isolated_cache_path.exists()
    with pytest.raises(requests.exceptions.RequestException):
        rules_cache.get_rules(_OfflineClient())


def test_corrupted_cache_reraises_the_original_request_exception_not_a_json_error(isolated_cache_path):
    """Regression test for a real, confirmed bug: get_rules() had no
    try/except around the cache read, so a corrupted cache file (write_text()
    isn't atomic -- a killed process, full disk, or power loss mid-write can
    leave it truncated) raised a raw json.JSONDecodeError instead of the
    RequestException every caller of get_rules() is built to catch.
    watcher.py's real-time handler and commands.py's retry_pending_files
    both specifically catch RequestException to mean "queue this for retry
    later" -- a JSONDecodeError fell through to their broader
    except-Exception fallback instead, which gives up permanently rather
    than retrying (see test_commands.py for that exact end-to-end
    consequence). A corrupted cache carries no more real information than
    no cache at all, so it must fail exactly the same way."""
    isolated_cache_path.write_text("{not valid json")

    with pytest.raises(requests.exceptions.RequestException):
        rules_cache.get_rules(_OfflineClient())


def test_empty_cache_file_reraises_the_original_request_exception(isolated_cache_path):
    isolated_cache_path.write_text("")

    with pytest.raises(requests.exceptions.RequestException):
        rules_cache.get_rules(_OfflineClient())


# ---------------------------------------------------------------------------
# Concurrent-write safety audit -- get_rules() has no lock around
# CACHE_PATH.write_text(), and AgentDownloadHandler spawns a brand new
# thread per filesystem event (agent/watcher.py), so multiple threads can
# genuinely call get_rules() -- and therefore write the cache -- at the
# same time. These tests use deterministic synchronization (a paced
# write_text() and a real threading.Barrier) to force the exact overlap
# instead of hoping timing produces it, and exercise the real get_rules()
# implementation throughout, not a reimplementation of its logic.
# ---------------------------------------------------------------------------


def test_reader_during_a_paused_write_sees_the_same_safe_fallback_as_an_empty_cache(
    isolated_cache_path, monkeypatch
):
    """CACHE_PATH.write_text() -- confirmed via CPython's own pathlib
    source -- opens the destination in 'w' mode, which truncates it to
    empty at OPEN time, before the actual content is ever written/flushed.
    That means there is a real, reachable instant, while one thread is
    mid-write, where the cache file genuinely exists but is empty on disk.
    This test forces a second thread's read to land in exactly that
    instant (not hoped-for timing) and confirms it's already handled: an
    empty file fails json.loads() exactly like the already-fixed corrupted-
    cache case, and re-raises the reader's own original RequestException --
    the identical, already-tested contract as test_empty_cache_file_
    reraises_the_original_request_exception above, just reached via a real
    concurrent writer instead of a pre-seeded empty file."""
    truncated = threading.Event()
    release = threading.Event()
    original_write_text = pathlib.Path.write_text

    def _paced_write_text(self, data, encoding=None, errors=None, newline=None):
        if self == isolated_cache_path and not truncated.is_set():
            original_write_text(self, "", encoding=encoding)  # the real truncate-on-open moment
            truncated.set()
            assert release.wait(timeout=5), "test setup failed to release the paused writer"
        return original_write_text(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(pathlib.Path, "write_text", _paced_write_text)

    writer_thread = threading.Thread(target=rules_cache.get_rules, args=(_OkClient({"categories": {}}),))
    writer_thread.start()
    try:
        assert truncated.wait(timeout=5), "writer thread never reached the truncate point"

        # The cache file is genuinely, verifiably empty on disk right now.
        assert isolated_cache_path.read_text(encoding="utf-8") == ""

        with pytest.raises(requests.exceptions.RequestException):
            rules_cache.get_rules(_OfflineClient())
    finally:
        release.set()
        writer_thread.join(timeout=5)

    assert not writer_thread.is_alive(), "the paused writer must have completed"
    assert json.loads(isolated_cache_path.read_text(encoding="utf-8")) == {"categories": {}}


def test_concurrent_successful_writers_do_not_corrupt_the_cache_file(isolated_cache_path, monkeypatch):
    """Regression test for a real, confirmed bug, reproduced with precise,
    deterministic control over the exact open/write ordering rather than
    hoping timing produces it (an earlier, less-controlled version of this
    test using only a threading.Barrier caught this same corruption for
    real, but only in roughly 1 of 8 runs -- captured output:
    '{"categories": {"Images": [".png"]}}]}}', i.e. writer B's complete,
    valid, SHORTER json.dumps() output with 3 leftover trailing bytes from
    writer A's longer output still attached).

    Root cause, confirmed via CPython's own pathlib source: write_text()
    calls self.open(mode='w', ...), which truncates the destination to
    empty at OPEN time -- but the actual write() only happens later, once
    the caller writes to the returned handle. If writer B's handle is
    opened (truncating the file) and then, before B ever writes to it, an
    independent writer A fully opens+writes+closes a LONGER payload to the
    same path, the file is now A's length. When B's already-open, already-
    truncated handle finally does write its own SHORTER payload, that
    write() call only overwrites the first len(B) bytes of the
    now-longer file -- it does not truncate again -- leaving A's trailing
    bytes stuck on the end of B's otherwise complete, valid JSON.

    This test forces exactly that ordering by pausing writer B's handle
    open (via a real, unmodified pathlib.Path.open() call whose return is
    simply delayed) until writer A has had a fair, generous window to run
    to completion -- exercising the real get_rules() implementation
    throughout, not a reimplementation of its logic."""
    handle_opened = threading.Event()
    release_handle = threading.Event()
    real_path_open = pathlib.Path.open

    def _paced_open(self, mode="r", *args, **kwargs):
        # The real open() call -- this is what actually truncates the file
        # on disk when mode == "w", exactly as it would with no patching
        # at all. Only the *return* of this already-real, already-opened
        # handle back to write_text() is delayed.
        f = real_path_open(self, mode, *args, **kwargs)
        if self == isolated_cache_path and mode == "w" and not handle_opened.is_set():
            handle_opened.set()
            assert release_handle.wait(timeout=5), "writer B was never released"
        return f

    monkeypatch.setattr(pathlib.Path, "open", _paced_open)

    # B's JSON is the shorter of the two -- the exact shape needed to
    # reproduce leftover trailing bytes from A once B's stale, already-
    # truncated handle finally writes its own (shorter) content on top of
    # A's already-completed (longer) file.
    rules_b_short = {"categories": {"Images": [".png"]}}
    rules_a_long = {"categories": {"Documents": [".pdf"]}}
    results = {}

    def _run(key, client):
        results[key] = rules_cache.get_rules(client)

    t_b = threading.Thread(target=_run, args=("b", _OkClient(rules_b_short)))
    t_b.start()
    assert handle_opened.wait(timeout=5), "writer B's handle was never opened"

    t_a = threading.Thread(target=_run, args=("a", _OkClient(rules_a_long)))
    t_a.start()
    # A fair, generous window for A to run to completion independently --
    # pre-fix, nothing blocks it, so this reliably lets it finish before B
    # is released below. Post-fix (writes serialized under a lock), A
    # simply blocks on that lock instead for this same window, harmlessly,
    # and finishes only after B is released and its own write completes.
    time.sleep(0.3)

    release_handle.set()
    t_a.join(timeout=5)
    t_b.join(timeout=5)
    assert not t_a.is_alive() and not t_b.is_alive(), "a writer thread never completed"

    assert results["a"] == rules_a_long, "each caller must still get back its own correct live fetch"
    assert results["b"] == rules_b_short

    final_text = isolated_cache_path.read_text(encoding="utf-8")
    final = json.loads(final_text)  # must not raise -- a corrupted file fails right here
    assert final in (rules_a_long, rules_b_short), (
        f"the cache file after two racing writers must be one complete, valid "
        f"writer's data -- never a shorter writer's JSON with a longer writer's "
        f"leftover trailing bytes still attached. Got: {final_text!r}"
    )
