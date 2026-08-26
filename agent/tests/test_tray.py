"""Automated coverage for agent/tray.py -- the thin pystray adapter that
agent/main.py::main() hands its actual callbacks to. Traced against the
real implementation:

- run_tray() itself has no business logic: it builds a 5-item pystray.Menu
  (Open watched folder / Pause watching / Reconfigure... / separator /
  Quit) and a pystray.Icon, then blocks in icon.run(). Every callback
  wrapper (_toggle_pause/_open_folder/_reconfigure/_quit) just calls the
  corresponding on_* function it was given.
- The Pause item's `checked=lambda item: is_paused()` is re-evaluated by
  pystray every time the menu opens -- confirmed live here by making
  is_paused() return a different value on each call.
- _quit calls on_quit() *then* icon.stop() -- confirmed by order.
- Confirmed directly against the installed pystray package (_win32.py):
  a menu click is dispatched via `descriptors[index - 1](self)` inside
  _on_notify(), itself called from _mainloop()'s message pump, which is
  wrapped in nothing but a bare `except:` that logs via pystray's own
  logger and then tears the whole icon down in `finally:` -- ending
  icon.run(), and therefore run_tray() and main(). Since every other
  agent thread (watchdog's Observer, the command poller) is a daemon
  thread (confirmed in watchdog/utils/__init__.py's BaseThread), that
  doesn't just close the tray: it silently ends the whole process, with
  the only trace being one log line from a *different* logger than the
  agent's own "fileflow.agent" one. This was a confirmed, reachable bug
  (a failed Reconfigure or a deleted watch folder for Open Folder both
  raise) -- see the "does not propagate" tests below for the fix.

These tests never launch a real tray icon: pystray.Icon is replaced with
a fake that captures its constructor arguments and returns immediately
from run() instead of blocking in a real Windows message loop. The real
pystray.Menu/MenuItem classes are used unmodified -- they're pure data
structures that never touch the OS themselves, so exercising a captured
MenuItem's real __call__() is a faithful stand-in for a real menu click.
"""

import logging

import pytest

from agent import tray


class _FakeIcon:
    """Stands in for pystray.Icon -- captures what run_tray() constructed
    it with, and never runs a real (blocking) win32 message loop."""

    def __init__(self, name, icon_image, title, menu):
        self.name = name
        self.icon_image = icon_image
        self.title = title
        self.menu = menu
        self.stopped_count = 0

    def run(self):
        pass

    def stop(self):
        self.stopped_count += 1


@pytest.fixture()
def fake_icon(monkeypatch):
    captured = {}

    def _make(name, icon_image, title, menu):
        captured["icon"] = _FakeIcon(name, icon_image, title, menu)
        return captured["icon"]

    monkeypatch.setattr(tray.pystray, "Icon", _make)
    return captured


def _run(fake_icon, **overrides):
    kwargs = dict(
        is_paused=lambda: False,
        on_toggle_pause=lambda: None,
        on_open_folder=lambda: None,
        on_reconfigure=lambda: None,
        on_quit=lambda: None,
    )
    kwargs.update(overrides)
    tray.run_tray(**kwargs)
    return fake_icon["icon"]


def _item(icon, text):
    return next(i for i in icon.menu.items if i.text == text)


# ---------------------------------------------------------------------------
# Menu construction / wiring
# ---------------------------------------------------------------------------


def test_run_tray_constructs_the_expected_menu_items_in_order(fake_icon):
    icon = _run(fake_icon)

    assert [i.text for i in icon.menu.items] == [
        "Open watched folder",
        "Pause watching",
        "Reconfigure...",
        "- - - -",
        "Quit FileFlow Agent",
    ]


def test_run_tray_wires_the_icon_name_and_title(fake_icon):
    icon = _run(fake_icon)

    assert icon.name == "FileFlow Agent"
    assert icon.title == "FileFlow Agent"


def test_pause_menu_item_checked_state_reflects_is_paused_live(fake_icon):
    """The docstring's own claim: is_paused is re-checked every time the
    menu opens, not captured once as a snapshot at construction time."""
    states = iter([False, True, False])
    icon = _run(fake_icon, is_paused=lambda: next(states))
    pause_item = _item(icon, "Pause watching")

    assert pause_item.checked is False
    assert pause_item.checked is True
    assert pause_item.checked is False


def test_open_folder_menu_item_invokes_the_callback(fake_icon):
    calls = []
    icon = _run(fake_icon, on_open_folder=lambda: calls.append(1))

    _item(icon, "Open watched folder")(icon)

    assert calls == [1]


def test_pause_menu_item_invokes_the_toggle_callback(fake_icon):
    calls = []
    icon = _run(fake_icon, on_toggle_pause=lambda: calls.append(1))

    _item(icon, "Pause watching")(icon)

    assert calls == [1]


def test_reconfigure_menu_item_invokes_the_callback(fake_icon):
    calls = []
    icon = _run(fake_icon, on_reconfigure=lambda: calls.append(1))

    _item(icon, "Reconfigure...")(icon)

    assert calls == [1]


def test_quit_menu_item_invokes_on_quit_then_stops_the_icon(fake_icon):
    events = []
    icon = _run(fake_icon, on_quit=lambda: events.append("quit"))

    _item(icon, "Quit FileFlow Agent")(icon)

    assert events == ["quit"]
    assert icon.stopped_count == 1


def test_repeated_quit_is_safe(fake_icon):
    events = []
    icon = _run(fake_icon, on_quit=lambda: events.append("quit"))
    quit_item = _item(icon, "Quit FileFlow Agent")

    quit_item(icon)
    quit_item(icon)

    assert events == ["quit", "quit"]
    assert icon.stopped_count == 2


# ---------------------------------------------------------------------------
# Callback exception handling -- see the module docstring for the full
# trace of why an uncaught exception here is a real, confirmed bug, not a
# hypothetical one.
# ---------------------------------------------------------------------------


def test_reconfigure_callback_exception_does_not_propagate_into_pystray(fake_icon, caplog):
    """Reproduces the real scenario this bug is reachable through:
    AgentRuntime.apply_config() re-raises after an internal rollback (see
    the apply_config() audit), so a failed Reconfigure attempt raises
    exactly like this."""

    def _boom():
        raise OSError("simulated apply_config() failure")

    icon = _run(fake_icon, on_reconfigure=_boom)
    reconfigure_item = _item(icon, "Reconfigure...")

    with caplog.at_level(logging.ERROR, logger="fileflow.agent.tray"):
        reconfigure_item(icon)  # must not raise

    assert "simulated apply_config() failure" in caplog.text


def test_open_folder_callback_exception_does_not_propagate_into_pystray(fake_icon, caplog):
    """Reproduces the other realistic trigger: os.startfile() raises when
    the watched folder has been deleted or is otherwise inaccessible."""

    def _boom():
        raise OSError("simulated: folder no longer exists")

    icon = _run(fake_icon, on_open_folder=_boom)
    open_folder_item = _item(icon, "Open watched folder")

    with caplog.at_level(logging.ERROR, logger="fileflow.agent.tray"):
        open_folder_item(icon)  # must not raise

    assert "simulated: folder no longer exists" in caplog.text


def test_toggle_pause_callback_exception_does_not_propagate_into_pystray(fake_icon, caplog):
    def _boom():
        raise RuntimeError("simulated toggle failure")

    icon = _run(fake_icon, on_toggle_pause=_boom)
    pause_item = _item(icon, "Pause watching")

    with caplog.at_level(logging.ERROR, logger="fileflow.agent.tray"):
        pause_item(icon)  # must not raise

    assert "simulated toggle failure" in caplog.text


def test_quit_callback_exception_does_not_prevent_the_icon_from_stopping(fake_icon, caplog):
    """Quit's contract is stronger than the other three: the user clicked
    Quit, so the icon must still disappear even if shutdown() itself hit
    an internal error -- it must not get stuck showing a tray icon for an
    agent that failed to shut down cleanly."""

    def _boom():
        raise RuntimeError("simulated shutdown() failure")

    icon = _run(fake_icon, on_quit=_boom)
    quit_item = _item(icon, "Quit FileFlow Agent")

    with caplog.at_level(logging.ERROR, logger="fileflow.agent.tray"):
        quit_item(icon)  # must not raise

    assert "simulated shutdown() failure" in caplog.text
    assert icon.stopped_count == 1, "the icon must still stop even if on_quit() raised"
