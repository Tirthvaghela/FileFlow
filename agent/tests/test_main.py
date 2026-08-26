"""Automated regression coverage for AgentRuntime.apply_config() -- live
reconfiguration of the watch folder / backend URL / token without a process
restart. Traced against the actual implementation (agent/main.py) rather
than assumed:

- self.client.reconfigure(config) runs unconditionally, first -- token and
  backend_url changes take effect immediately regardless of whether the
  watch folder also changed.
- The watch folder is only touched if it actually differs (compared via
  .resolve()); when it's unchanged, the existing Observer/handler (and
  therefore its pause state) are left completely untouched.
- When the folder does change, a *new* AgentDownloadHandler is created --
  its manually_paused/remote_monitoring_disabled both start at their
  defaults (False), so manual pause is NOT carried over across a folder
  change. That's the existing, real contract, not something these tests
  invent.
- apply_config() itself never calls save_config() -- persistence is the
  setup wizard's responsibility (agent/setup_gui.py), not the runtime's.
- apply_config() performs no validation of its own on the incoming config;
  whatever `watch_folder` is given is handed straight to start_watching(),
  which creates it via mkdir(parents=True, exist_ok=True).
"""

from pathlib import Path

import agent.main as main
from agent import outbox
from agent.client import AgentClient
from agent.config import AgentConfig
from agent.watcher import start_watching

import pytest


def _config(watch_folder, backend_url="http://backend.test", token="test-token-a"):
    return AgentConfig(backend_url=backend_url, token=token, watch_folder=str(watch_folder))


def _make_runtime(config, outbox_conn):
    """Builds a real AgentRuntime without going through __init__. __init__
    also starts poll_forever() as a background daemon thread, which would
    make real network calls (against whatever fake backend_url a test uses)
    every few seconds for the rest of the test process's life -- exactly
    the kind of external, nondeterministic boundary the task calls out to
    mock. apply_config()/shutdown()/is_paused()/toggle_pause() only ever
    touch the instance attributes assigned here, so a manually-assembled
    instance exercises the exact same real method bodies; nothing about
    apply_config() itself is faked."""
    runtime = main.AgentRuntime.__new__(main.AgentRuntime)
    runtime.client = AgentClient(config)
    runtime.watch_root = config.watch_root
    runtime.outbox_conn = outbox_conn
    runtime.observer, runtime.handler = start_watching(
        runtime.client, runtime.watch_root, runtime.outbox_conn
    )
    return runtime


@pytest.fixture()
def outbox_conn(tmp_path):
    conn = outbox.open_queue(tmp_path / "outbox.db")
    yield conn
    conn.close()


@pytest.fixture()
def runtime(tmp_path, outbox_conn):
    rt = _make_runtime(_config(tmp_path / "folder_a"), outbox_conn)
    yield rt
    rt.observer.stop()
    rt.observer.join(timeout=5)


def test_apply_config_with_a_different_watch_folder_swaps_observer_and_handler(runtime, tmp_path):
    old_observer, old_handler = runtime.observer, runtime.handler
    folder_b = tmp_path / "folder_b"  # deliberately not created yet

    runtime.apply_config(_config(folder_b))

    assert runtime.watch_root == folder_b
    assert folder_b.is_dir(), "start_watching() must create a watch folder that doesn't exist yet"
    assert runtime.handler.watch_root == folder_b
    assert runtime.observer is not old_observer
    assert runtime.handler is not old_handler
    assert runtime.observer.is_alive() is True, "the new watcher must be running"
    assert old_observer.is_alive() is False, "the old watcher must be fully stopped -- no duplicate watching folder_a"


def test_apply_config_with_the_same_watch_folder_leaves_observer_and_handler_untouched(runtime):
    old_observer, old_handler = runtime.observer, runtime.handler

    runtime.apply_config(_config(runtime.watch_root))

    assert runtime.observer is old_observer, "a no-op folder change must not restart the watcher"
    assert runtime.handler is old_handler
    assert runtime.observer.is_alive() is True


def test_apply_config_preserves_manual_pause_when_watch_folder_is_unchanged(runtime):
    runtime.handler.manually_paused = True

    runtime.apply_config(_config(runtime.watch_root))

    assert runtime.handler.manually_paused is True


def test_apply_config_resets_pause_state_on_the_new_handler_when_watch_folder_changes(runtime, tmp_path):
    """Documents the existing, real contract -- not a design opinion. A
    folder change creates a brand new AgentDownloadHandler, and pause state
    lives on that handler instance, so it does not carry over. If this is
    ever meant to change, that's a deliberate product decision, not
    something this test should silently paper over."""
    runtime.handler.manually_paused = True

    runtime.apply_config(_config(tmp_path / "folder_b"))

    assert runtime.handler.manually_paused is False


def test_apply_config_updates_client_token_and_backend_url_immediately(runtime):
    runtime.apply_config(
        _config(runtime.watch_root, backend_url="http://new-backend.test", token="test-token-b")
    )

    assert runtime.client.base_url == "http://new-backend.test"
    assert runtime.client.session.headers["Authorization"] == "Bearer test-token-b"


def test_apply_config_updates_client_even_when_the_watch_folder_also_changes(runtime, tmp_path):
    runtime.apply_config(
        _config(tmp_path / "folder_b", backend_url="http://new-backend.test", token="test-token-b")
    )

    assert runtime.client.base_url == "http://new-backend.test"
    assert runtime.client.session.headers["Authorization"] == "Bearer test-token-b"


def test_reapplying_the_same_config_twice_does_not_create_extra_observers(runtime):
    same = _config(runtime.watch_root)

    runtime.apply_config(same)
    first_observer = runtime.observer
    runtime.apply_config(same)

    assert runtime.observer is first_observer


def test_apply_config_does_not_persist_configuration_itself(runtime, tmp_path, monkeypatch):
    """apply_config() only ever applies runtime state -- persisting the new
    config to disk is the setup wizard's job (agent/setup_gui.py calls
    save_config() before apply_config() is ever invoked with the result).
    A regression that started calling save_config() from inside
    apply_config() itself would be a real, surprising behavior change."""
    calls = []
    monkeypatch.setattr("agent.config.save_config", lambda *a, **k: calls.append((a, k)))

    runtime.apply_config(_config(tmp_path / "folder_b", token="test-token-b"))

    assert calls == []


def test_apply_config_keeps_the_old_watcher_alive_if_starting_the_new_one_fails(runtime, monkeypatch):
    """Regression test for a real, traced bug: apply_config() used to stop
    the old Observer and reassign self.watch_root to the new folder BEFORE
    attempting to start the replacement watcher. If start_watching() then
    raised, self.observer/self.handler were left pointing at the old,
    already-stopped watcher while self.watch_root claimed the new folder --
    an inconsistent state where nothing was actually being watched, with no
    rollback, until the whole process was restarted."""
    old_observer, old_handler, old_root = runtime.observer, runtime.handler, runtime.watch_root

    def failing_start_watching(client, watch_root, outbox_conn):
        raise OSError("simulated watcher startup failure")

    monkeypatch.setattr(main, "start_watching", failing_start_watching)

    with pytest.raises(OSError):
        runtime.apply_config(_config(old_root / "unreachable"))

    assert runtime.observer is old_observer, "the working watcher must not be discarded on a failed swap"
    assert runtime.handler is old_handler
    assert runtime.watch_root == old_root, "must not claim to be watching a folder nothing is watching"
    assert runtime.observer.is_alive() is True, "the original watcher must still actually be running"


# ---------------------------------------------------------------------------
# main() -- singleton-gated startup. Traced against the real implementation:
# `if not singleton.acquire(): notify(...); return` is the very first thing
# main() does, before CONFIG_PATH.exists()/load_config()/run_setup_wizard()/
# AgentRuntime()/run_tray() are ever touched. Proven below by making every
# one of those later steps raise if it's ever reached.
# ---------------------------------------------------------------------------


def test_main_exits_early_without_starting_anything_when_the_singleton_is_already_held(monkeypatch):
    monkeypatch.setattr(main.singleton, "acquire", lambda: False)
    notified = []
    monkeypatch.setattr(main, "notify", lambda *a, **k: notified.append((a, k)))

    def _must_not_be_called(*a, **k):
        raise AssertionError("must not run when the singleton lock isn't held")

    monkeypatch.setattr(main, "load_config", _must_not_be_called)
    monkeypatch.setattr(main, "run_setup_wizard", _must_not_be_called)
    monkeypatch.setattr(main, "AgentRuntime", _must_not_be_called)
    monkeypatch.setattr(main, "run_tray", _must_not_be_called)

    main.main()  # must return normally, not raise

    assert notified, "the user should be told another instance is already running"


# ---------------------------------------------------------------------------
# open_folder() -- the tray's "Open watched folder" action. Traced: a
# direct os.startfile(str(self.watch_root)) call, no subprocess/shell
# involved at all (so no shell-metacharacter injection surface exists --
# os.startfile takes a path directly, never builds a command line). No
# try/except of its own -- the tray layer (agent/tray.py, see
# test_tray.py) is what now catches a failure here, not this method.
# ---------------------------------------------------------------------------


def test_open_folder_calls_os_startfile_with_the_watch_root(runtime, monkeypatch):
    calls = []
    monkeypatch.setattr(main.os, "startfile", lambda path: calls.append(path))

    runtime.open_folder()

    assert calls == [str(runtime.watch_root)]


def test_open_folder_propagates_a_failure_unchanged(runtime, monkeypatch):
    """Documents the real, existing contract: AgentRuntime.open_folder()
    itself has no error handling -- a raised OSError (deleted/inaccessible
    folder) propagates straight out of this method. Safety against that
    now lives one layer up, in agent/tray.py's callback wrapper."""

    def _fail(path):
        raise OSError("simulated: folder no longer exists")

    monkeypatch.setattr(main.os, "startfile", _fail)

    with pytest.raises(OSError):
        runtime.open_folder()


# ---------------------------------------------------------------------------
# is_paused() after a folder-changing reconfigure -- the exact live value
# agent/tray.py's Pause menu item's checked state reads on every menu
# open. Ties directly to the already-established, unchanged contract
# (test_apply_config_resets_pause_state_on_the_new_handler_when_watch_folder_changes
# above): a folder change creates a brand new handler, whose
# manually_paused starts False, so is_paused() reports False even though
# the agent was manually paused moments before the reconfigure.
# ---------------------------------------------------------------------------


def test_is_paused_reflects_the_reset_after_a_reconfigure_that_changes_the_folder(runtime, tmp_path):
    runtime.handler.manually_paused = True
    assert runtime.is_paused() is True

    runtime.apply_config(_config(tmp_path / "folder_b"))

    assert runtime.is_paused() is False, "the tray's live checked-state must reflect the new handler's reset"


# ---------------------------------------------------------------------------
# on_reconfigure() -- the closure main() builds and hands to run_tray() as
# its on_reconfigure callback. Traced: `current = load_config(); updated =
# run_setup_wizard(existing=current); if updated is not None:
# runtime.apply_config(updated)`. Captured here by driving main() itself
# through with everything mocked, then invoking the real closure directly
# for each of the three scenarios the audit's task called out.
# ---------------------------------------------------------------------------


class _FakeRuntimeForReconfigure:
    """Minimal stand-in exposing every attribute main() wires into
    run_tray()'s kwargs -- only apply_config() is actually exercised by
    these tests, but main() reads the others while constructing the
    kwargs dict, so they must exist."""

    def __init__(self):
        self.applied = []

    def apply_config(self, config):
        self.applied.append(config)

    def is_paused(self):
        return False

    def toggle_pause(self):
        pass

    def open_folder(self):
        pass

    def shutdown(self):
        pass


def _boot_main_and_capture_on_reconfigure(monkeypatch, fake_runtime):
    monkeypatch.setattr(main.singleton, "acquire", lambda: True)
    monkeypatch.setattr(main, "CONFIG_PATH", Path(__file__))  # any real, existing path
    monkeypatch.setattr(main, "load_config", lambda: _config("C:/initial"))
    monkeypatch.setattr(main, "AgentRuntime", lambda config: fake_runtime)
    monkeypatch.setattr(main, "notify", lambda *a, **k: None)
    captured = {}
    monkeypatch.setattr(main, "run_tray", lambda **kwargs: captured.update(kwargs))

    main.main()

    return captured["on_reconfigure"]


def test_on_reconfigure_does_nothing_when_the_wizard_is_cancelled(monkeypatch):
    fake_runtime = _FakeRuntimeForReconfigure()
    on_reconfigure = _boot_main_and_capture_on_reconfigure(monkeypatch, fake_runtime)
    monkeypatch.setattr(main, "run_setup_wizard", lambda existing: None)

    on_reconfigure()

    assert fake_runtime.applied == [], "a cancelled wizard must never call apply_config()"


def test_on_reconfigure_applies_the_new_config_when_the_wizard_saves(monkeypatch):
    fake_runtime = _FakeRuntimeForReconfigure()
    on_reconfigure = _boot_main_and_capture_on_reconfigure(monkeypatch, fake_runtime)
    new_config = _config("C:/new_folder")
    monkeypatch.setattr(main, "run_setup_wizard", lambda existing: new_config)

    on_reconfigure()

    assert fake_runtime.applied == [new_config]


def test_on_reconfigure_propagates_an_apply_config_failure_unchanged(monkeypatch):
    """Documents the real, existing contract: this closure has no
    try/except of its own -- a raised apply_config() failure (e.g. the
    already-audited watcher-swap error, which re-raises even after its own
    internal rollback) propagates straight out of on_reconfigure(). Safety
    against that now lives one layer up, in agent/tray.py's callback
    wrapper (see test_tray.py) -- not duplicated here."""

    class _FailingRuntime(_FakeRuntimeForReconfigure):
        def apply_config(self, config):
            super().apply_config(config)
            raise OSError("simulated apply_config() failure")

    fake_runtime = _FailingRuntime()
    on_reconfigure = _boot_main_and_capture_on_reconfigure(monkeypatch, fake_runtime)
    monkeypatch.setattr(main, "run_setup_wizard", lambda existing: _config("C:/new_folder"))

    with pytest.raises(OSError):
        on_reconfigure()

    assert len(fake_runtime.applied) == 1, "apply_config() must still have actually been attempted"


def test_on_reconfigure_notifies_the_user_when_apply_config_fails(monkeypatch):
    """Regression test for a real, confirmed UX gap in the reconfigure
    lifecycle: run_setup_wizard() already calls save_config() and closes
    its window (looking exactly like a success to the user) *before*
    apply_config() is ever attempted -- on_reconfigure() only calls it
    after the wizard has already returned. Without this notify() call, a
    failed reconfigure was completely invisible to the user: the wizard
    closed normally, and the failure was only ever logged (see
    agent/tray.py's callback-exception handling, fixed in an earlier
    task) -- never surfaced anywhere the user would see it, leaving them
    with no way to know the agent was still silently running on its old
    configuration while config.json already held the new, unapplied one."""

    class _FailingRuntime(_FakeRuntimeForReconfigure):
        def apply_config(self, config):
            super().apply_config(config)
            raise OSError("simulated apply_config() failure")

    fake_runtime = _FailingRuntime()
    on_reconfigure = _boot_main_and_capture_on_reconfigure(monkeypatch, fake_runtime)
    monkeypatch.setattr(main, "run_setup_wizard", lambda existing: _config("C:/new_folder"))
    notifications = []
    monkeypatch.setattr(main, "notify", lambda *a, **k: notifications.append(a))

    with pytest.raises(OSError):
        on_reconfigure()

    assert notifications, "the user must be told the reconfigure failed, not left to assume it worked"
