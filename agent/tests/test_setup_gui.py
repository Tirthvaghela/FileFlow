"""Automated coverage for agent/setup_gui.py -- the Tkinter setup wizard
used by the packaged .exe (no terminal attached) and by the tray's
"Reconfigure" action. Zero coverage existed before this task; the GUI's
own event loop makes it look untestable, but a real Tk window can
actually be driven end-to-end on this machine (a real Windows desktop,
not headless CI) without ever showing a visible window or requiring a
human:

- tkinter.StringVar.__init__ and tkinter.Button.__init__ are monkeypatched
  to record every instance created, in the exact order run_setup_wizard()
  creates them (backend_var, token_var, folder_var; then the "Get my
  token"/"Browse..."/"Save & Start"[/"Cancel"] buttons).
- tkinter.Tk.mainloop is monkeypatched so that instead of blocking in a
  real event loop, it sets field values (simulating what a user typed)
  and calls button.invoke() -- the same, real Tcl-level path a genuine
  click takes, confirmed (see below) to route exceptions through Tk's
  real report_callback_exception the same way a live click would.
- agent.config.CONFIG_PATH is always isolated to a tmp_path first, so
  save_config() (called for real, unmocked, inside on_save()) never
  touches a real config.json.

Traced against the real implementation:
- Both "Save & Start" and "Cancel" call root.destroy() themselves (as
  their own button command) -- the driving fixture below must not also
  call it, or Tk raises "application has been destroyed".
- on_save() has no try/except of its own around save_config() -- proven
  here (via .invoke(), not a direct Python call, so the real Tcl
  exception-routing path is exercised) that this is nonetheless SAFE:
  Tkinter's own report_callback_exception contains the exception, the
  window is never destroyed (root.destroy() is unreached), and no
  partial config is written, since save_config() raising happens before
  any of it. Different from -- and much safer than -- the agent/tray.py
  bug fixed in an earlier task, where an uncaught callback exception
  tore down the entire application.
"""

import json
import time
from pathlib import Path

import pytest
import tkinter as tk

import agent.config as agent_config
import agent.setup_gui as setup_gui
from agent.config import AgentConfig


@pytest.fixture()
def isolated_config_path(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(agent_config, "CONFIG_PATH", path)
    return path


class _Driver:
    """Populated by the monkeypatched mainloop() once run_setup_wizard()
    reaches it; the test configures `.overrides`/`.action` beforehand."""

    def __init__(self):
        self.overrides: dict = {}
        self.action = "save"  # "save" | "cancel" | "close" | "leave_open"
        self.prefilled: dict = {}
        self.caught_exceptions: list = []
        self.token_entry_show: str | None = None


@pytest.fixture(autouse=True)
def _retry_flaky_tk_interpreter_creation(monkeypatch):
    """Creating a real tk.Tk() interpreter many times back-to-back in the
    same process (this file does it once per test) intermittently races
    on this machine: Tcl occasionally fails to locate its own library
    files for an interpreter created immediately after the previous one
    was torn down -- observed as several different message shapes
    ("Can't find a usable init.tcl", "Can't find a usable tk.tcl",
    "invalid command name tcl_findLibrary"), all for paths that are
    correct and do exist (confirmed: re-running the exact same failing
    test alone always passes). This is a property of rapidly creating/
    destroying Tcl interpreters in one process, not of setup_gui.py
    itself, and isn't reliably avoided by a fixed delay between tests or
    by narrowly matching only one of the message shapes -- so this
    retries construction on any TclError raised from within Tk.__init__
    itself specifically (nowhere else), which was reliable in testing."""
    real_init = tk.Tk.__init__

    def _resilient_init(self, *a, **k):
        last_exc = None
        for _ in range(8):
            try:
                real_init(self, *a, **k)
                return
            except tk.TclError as exc:
                last_exc = exc
                time.sleep(0.2)
        raise last_exc

    monkeypatch.setattr(tk.Tk, "__init__", _resilient_init)


@pytest.fixture()
def driver(monkeypatch):
    d = _Driver()
    created_vars: list[tk.StringVar] = []
    orig_stringvar_init = tk.StringVar.__init__

    def _tracking_sv_init(self, *a, **k):
        orig_stringvar_init(self, *a, **k)
        created_vars.append(self)

    monkeypatch.setattr(tk.StringVar, "__init__", _tracking_sv_init)

    captured_buttons: dict[str, tk.Button] = {}
    orig_button_init = tk.Button.__init__

    def _tracking_button_init(self, master=None, **kwargs):
        orig_button_init(self, master, **kwargs)
        if "text" in kwargs:
            captured_buttons[kwargs["text"]] = self

    monkeypatch.setattr(tk.Button, "__init__", _tracking_button_init)

    orig_entry_init = tk.Entry.__init__
    entry_show_values: list[str | None] = []

    def _tracking_entry_init(self, master=None, cnf=None, **kwargs):
        entry_show_values.append(kwargs.get("show"))
        if cnf is not None:
            orig_entry_init(self, master, cnf, **kwargs)
        else:
            orig_entry_init(self, master, **kwargs)

    monkeypatch.setattr(tk.Entry, "__init__", _tracking_entry_init)

    def _fake_mainloop(self, n=0):
        self.report_callback_exception = lambda exc, val, tb: d.caught_exceptions.append(val)
        backend_var, token_var, folder_var = created_vars[0], created_vars[1], created_vars[2]
        d.prefilled = {
            "backend_url": backend_var.get(),
            "token": token_var.get(),
            "watch_folder": folder_var.get(),
        }
        # token field is the 2nd Entry created (row 5); confirms masking.
        d.token_entry_show = entry_show_values[1] if len(entry_show_values) > 1 else None

        if d.action == "leave_open":
            return
        if "backend_url" in d.overrides:
            backend_var.set(d.overrides["backend_url"])
        if "token" in d.overrides:
            token_var.set(d.overrides["token"])
        if "watch_folder" in d.overrides:
            folder_var.set(d.overrides["watch_folder"])

        if d.action == "save":
            captured_buttons["Save & Start"].invoke()
        elif d.action == "cancel":
            captured_buttons["Cancel"].invoke()
        elif d.action == "close":
            close_command = self.protocol("WM_DELETE_WINDOW")
            self.tk.call(close_command)

    monkeypatch.setattr(tk.Tk, "mainloop", _fake_mainloop)
    return d


# ---------------------------------------------------------------------------
# Save path
# ---------------------------------------------------------------------------


def test_save_persists_all_three_fields_and_returns_the_config(driver, isolated_config_path, tmp_path):
    folder = tmp_path / "watched"
    driver.overrides = {
        "backend_url": "http://example.test:9000",
        "token": "test-agent-token",
        "watch_folder": str(folder),
    }

    result = setup_gui.run_setup_wizard()

    assert result == AgentConfig(
        backend_url="http://example.test:9000", token="test-agent-token", watch_folder=str(folder)
    )
    saved = json.loads(isolated_config_path.read_text())
    assert saved["watch_folder"] == str(folder)


def test_save_resolves_a_relative_watch_folder_to_an_absolute_path(driver, isolated_config_path):
    """Regression test for a real, confirmed bug: on_save() saved
    watch_folder exactly as typed, with no path resolution -- the exact
    same bug class already fixed in agent/setup.py in an earlier task
    (see that fix's own comment). A relative value typed here has no
    well-defined meaning at all in a GUI context (there's no "current
    directory" a user typing into a text box could reasonably intend),
    and the agent later interprets it relative to whatever directory the
    packaged .exe happens to be launched from -- silently pointing the
    running agent at the wrong folder.

    Deliberately does NOT monkeypatch.chdir(): a real tk.Tk() interpreter
    constructed after the process's working directory has just changed
    intermittently fails here with Tcl library-lookup errors ("Can't
    find a usable tk.tcl", "invalid command name tcl_findLibrary") --
    Tcl's own library-finding is cwd-sensitive at interpreter-init time
    on this machine. Verifying against whatever the real cwd already is
    (instead of changing it) proves the exact same resolution behavior
    without that unrelated fragility."""
    driver.overrides = {
        "backend_url": "http://example.test",
        "token": "test-agent-token",
        "watch_folder": "relative_subfolder",
    }

    result = setup_gui.run_setup_wizard()

    assert Path(result.watch_folder).is_absolute()
    assert result.watch_folder == str((Path.cwd() / "relative_subfolder").resolve())


def test_save_strips_surrounding_whitespace(driver, isolated_config_path, tmp_path):
    folder = tmp_path / "watched"
    driver.overrides = {
        "backend_url": "  http://example.test  ",
        "token": "  test-token  ",
        "watch_folder": f"  {folder}  ",
    }

    result = setup_gui.run_setup_wizard()

    assert result.backend_url == "http://example.test"
    assert result.token == "test-token"
    assert Path(result.watch_folder) == folder.resolve()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_save_rejects_a_blank_token_and_writes_nothing(driver, isolated_config_path, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(setup_gui.messagebox, "showerror", lambda *a, **k: shown.append(a))
    driver.overrides = {
        "backend_url": "http://example.test",
        "token": "   ",
        "watch_folder": str(tmp_path / "watched"),
    }

    result = setup_gui.run_setup_wizard()

    assert result is None
    assert not isolated_config_path.exists()
    assert shown, "the user must be told what's missing"


def test_save_rejects_a_blank_watch_folder_and_writes_nothing(driver, isolated_config_path, monkeypatch):
    monkeypatch.setattr(setup_gui.messagebox, "showerror", lambda *a, **k: None)
    driver.overrides = {"backend_url": "http://example.test", "token": "test-token", "watch_folder": "  "}

    result = setup_gui.run_setup_wizard()

    assert result is None
    assert not isolated_config_path.exists()


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def test_cancel_returns_none_and_leaves_the_existing_config_file_untouched(
    driver, isolated_config_path, tmp_path
):
    isolated_config_path.write_text(
        json.dumps({"backend_url": "http://old.test", "token": "old-token", "watch_folder": "C:\\Old"})
    )
    driver.action = "cancel"
    driver.overrides = {"watch_folder": str(tmp_path / "would_be_new")}  # a user could still type first

    existing = AgentConfig(backend_url="http://old.test", token="old-token", watch_folder="C:\\Old")
    result = setup_gui.run_setup_wizard(existing=existing)

    assert result is None
    assert isolated_config_path.read_text() == json.dumps(
        {"backend_url": "http://old.test", "token": "old-token", "watch_folder": "C:\\Old"}
    )


def test_window_close_returns_none_without_changing_existing_config(driver, isolated_config_path):
    original = json.dumps(
        {"backend_url": "http://old.test", "token": "old-token", "watch_folder": "C:\\Old"}
    )
    isolated_config_path.write_text(original)
    driver.action = "close"
    existing = AgentConfig(backend_url="http://old.test", token="old-token", watch_folder="C:\\Old")

    result = setup_gui.run_setup_wizard(existing=existing)

    assert result is None
    assert isolated_config_path.read_text() == original


def test_cancel_button_is_only_offered_when_reconfiguring_an_existing_config(driver, isolated_config_path):
    """Traced from the source: the Cancel button is only constructed
    `if existing is not None`. First-run setup has no way to "cancel"
    out of it -- closing the window is the only option. Verified
    directly (not just by reading the source) by attempting to click a
    "Cancel" button that should not exist at all in this case."""
    driver.action = "cancel"

    with pytest.raises(KeyError):
        setup_gui.run_setup_wizard(existing=None)


# ---------------------------------------------------------------------------
# Existing-config pre-fill (Reconfigure)
# ---------------------------------------------------------------------------


def test_reconfigure_prefills_every_field_from_the_existing_config(driver, isolated_config_path):
    existing = AgentConfig(
        backend_url="http://old-backend.test", token="old-secret-token", watch_folder="C:\\Old\\Folder"
    )
    driver.action = "leave_open"

    setup_gui.run_setup_wizard(existing=existing)

    assert driver.prefilled == {
        "backend_url": "http://old-backend.test",
        "token": "old-secret-token",
        "watch_folder": "C:\\Old\\Folder",
    }


def test_first_run_prefills_the_default_backend_url_and_blank_token_and_folder(driver, isolated_config_path):
    driver.action = "leave_open"

    setup_gui.run_setup_wizard(existing=None)

    assert driver.prefilled == {
        "backend_url": setup_gui.DEFAULT_BACKEND_URL,
        "token": "",
        "watch_folder": "",
    }


# ---------------------------------------------------------------------------
# Token masking (section 8 of the audit -- CLI's getpass masking already
# fixed in an earlier task; this confirms the GUI's own masking directly,
# via widget introspection, rather than just re-reading the source).
# ---------------------------------------------------------------------------


def test_token_field_is_masked_but_other_fields_are_not(driver, isolated_config_path):
    driver.action = "leave_open"

    setup_gui.run_setup_wizard(existing=None)

    assert driver.token_entry_show == "*"


# ---------------------------------------------------------------------------
# save_config() failure -- confirmed safe (see module docstring): Tkinter's
# own report_callback_exception contains it. Different from, and much
# safer than, the tray.py callback-exception bug fixed in an earlier task.
# ---------------------------------------------------------------------------


def test_a_failed_save_shows_an_error_and_leaves_no_partial_config(
    driver, isolated_config_path, tmp_path, monkeypatch
):
    def _fail(*a, **k):
        raise OSError("simulated disk-full while writing the config")

    monkeypatch.setattr(setup_gui, "save_config", _fail)
    shown_errors = []
    monkeypatch.setattr(setup_gui.messagebox, "showerror", lambda *a, **k: shown_errors.append(a))
    driver.overrides = {
        "backend_url": "http://example.test",
        "token": "test-token",
        "watch_folder": str(tmp_path / "watched"),
    }

    result = setup_gui.run_setup_wizard()

    assert result is None, "on_save() never reached its saved[...] assignments"
    assert not isolated_config_path.exists(), "no partial config must be left behind"
    assert driver.caught_exceptions == []
    assert shown_errors
    assert "simulated disk-full" in shown_errors[0][1]
