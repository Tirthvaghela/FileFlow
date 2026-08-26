"""Automated coverage for agent/setup.py -- the plain-CLI, input()-based
setup path used when running from source with a terminal attached (as
opposed to setup_gui.py's Tkinter wizard, used by the packaged .exe and by
Reconfigure). Traced against the real implementation:

- Exactly one write: save_config(backend_url, token, watch_folder), called
  only after both token and watch_folder pass a non-empty check. Nothing
  is ever partially written -- either all three prompts are answered and
  the single write happens, or a SystemExit happens first and nothing is
  written at all.
- setup.py never calls load_config() -- it has no notion of "existing"
  config to pre-fill or preserve, unlike setup_gui.py's `existing` param.
  Re-running it always blindly overwrites, matching its own docstring
  ("One-time interactive setup").
- backend_url falls back to a default when left blank; token and
  watch_folder are required (SystemExit if blank after stripping).
- The token is collected via getpass.getpass() rather than input(), so it
  isn't echoed to the terminal while typed -- matching setup_gui.py's
  show="*" masking on its equivalent field. backend_url and watch_folder
  still use ordinary input().
"""

import json
from pathlib import Path

import pytest

import agent.config as agent_config
import agent.setup as agent_setup


@pytest.fixture()
def isolated_config_path(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(agent_config, "CONFIG_PATH", path)
    return path


def _answer(monkeypatch, backend_url, token, watch_folder):
    """backend_url and watch_folder are read via input(), in that order;
    the token is read separately via getpass.getpass() in between."""
    responses = iter([backend_url, watch_folder])
    monkeypatch.setattr("builtins.input", lambda *a: next(responses))
    monkeypatch.setattr("getpass.getpass", lambda *a: token)


def test_setup_resolves_a_relative_watch_folder_to_an_absolute_path(
    tmp_path, isolated_config_path, monkeypatch
):
    """Regression test for a real, traced bug: setup.py persisted the watch
    folder exactly as typed, with no path resolution. A relative value
    (e.g. "Downloads") is only meaningful relative to whatever directory
    `python -m agent.setup` happened to be run from -- but the *agent*
    later interprets that same string relative to whatever directory
    `python -m agent.main` happens to be launched from instead (Windows
    Startup, a shortcut with a different "Start in" folder, ...), which is
    not guaranteed to match. That silently points the running agent at an
    entirely different folder than the one the user actually chose."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    _answer(monkeypatch, "", "test-token", "relative_subfolder")

    agent_setup.main()

    saved = json.loads(isolated_config_path.read_text())
    assert Path(saved["watch_folder"]).is_absolute()
    assert saved["watch_folder"] == str((workdir / "relative_subfolder").resolve())


def test_setup_creates_a_config_that_load_config_can_immediately_read_back(
    isolated_config_path, monkeypatch, tmp_path
):
    watch_folder = tmp_path / "watched"
    _answer(monkeypatch, "http://example.test:9000", "test-token-a", str(watch_folder))

    agent_setup.main()

    loaded = agent_config.load_config()
    assert loaded.backend_url == "http://example.test:9000"
    assert loaded.token == "test-token-a"
    assert Path(loaded.watch_folder) == watch_folder.resolve()


def test_setup_defaults_backend_url_when_left_blank(isolated_config_path, monkeypatch, tmp_path):
    _answer(monkeypatch, "   ", "test-token", str(tmp_path / "watched"))

    agent_setup.main()

    saved = json.loads(isolated_config_path.read_text())
    assert saved["backend_url"] == "http://localhost:8000"


def test_setup_rejects_empty_token_and_writes_nothing(isolated_config_path, monkeypatch, tmp_path):
    _answer(monkeypatch, "", "   ", str(tmp_path / "watched"))

    with pytest.raises(SystemExit):
        agent_setup.main()

    assert not isolated_config_path.exists()


def test_setup_rejects_empty_watch_folder_and_writes_nothing(isolated_config_path, monkeypatch):
    _answer(monkeypatch, "", "test-token", "   ")

    with pytest.raises(SystemExit):
        agent_setup.main()

    assert not isolated_config_path.exists()


def test_setup_blindly_overwrites_an_existing_config(isolated_config_path, monkeypatch, tmp_path):
    """setup.py never reads the existing file -- documented ("One-time
    interactive setup"), not a bug. Re-running it always replaces whatever
    was there, in full, with the newly typed values."""
    isolated_config_path.write_text(
        json.dumps({"backend_url": "http://old.test", "token": "old-token", "watch_folder": "C:\\Old"})
    )
    new_folder = tmp_path / "new_watched"
    _answer(monkeypatch, "http://new.test", "new-token", str(new_folder))

    agent_setup.main()

    saved = json.loads(isolated_config_path.read_text())
    assert saved["backend_url"] == "http://new.test"
    assert saved["token"] == "new-token"
    assert Path(saved["watch_folder"]) == new_folder.resolve()


def test_setup_succeeds_even_when_the_existing_config_is_corrupted(
    isolated_config_path, monkeypatch, tmp_path
):
    """setup.py never calls load_config(), so a corrupted existing file
    (truncated JSON, missing keys, ...) can never block or crash it --
    re-running setup is always a safe way to recover from a broken config,
    without needing the corrupted-config handling load_config() itself
    has."""
    isolated_config_path.write_text("{not valid json at all")
    new_folder = tmp_path / "recovered"
    _answer(monkeypatch, "", "recovery-token", str(new_folder))

    agent_setup.main()

    loaded = agent_config.load_config()
    assert loaded.token == "recovery-token"


def test_setup_strips_surrounding_whitespace_from_every_field(
    isolated_config_path, monkeypatch, tmp_path
):
    folder = tmp_path / "watched"
    _answer(monkeypatch, "  http://example.test  ", "  test-token  ", f"  {folder}  ")

    agent_setup.main()

    saved = json.loads(isolated_config_path.read_text())
    assert saved["backend_url"] == "http://example.test"
    assert saved["token"] == "test-token"
    assert Path(saved["watch_folder"]) == folder.resolve()


# ---------------------------------------------------------------------------
# getpass.getpass() token masking -- security hardening added so the token
# isn't echoed to the terminal while typed, matching setup_gui.py's existing
# show="*" masking on its equivalent field.
# ---------------------------------------------------------------------------


def test_setup_obtains_the_token_via_getpass_not_input(isolated_config_path, monkeypatch, tmp_path):
    """The core guarantee this task exists for: the token prompt must go
    through getpass.getpass(), not the ordinary, terminal-echoing input()
    still used for backend_url and watch_folder."""
    folder = tmp_path / "watched"
    input_responses = iter(["http://example.test", str(folder)])
    input_calls = []
    getpass_calls = []

    def fake_input(prompt=""):
        input_calls.append(prompt)
        return next(input_responses)

    def fake_getpass(prompt=""):
        getpass_calls.append(prompt)
        return "test-agent-token"

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr("getpass.getpass", fake_getpass)

    agent_setup.main()

    assert len(getpass_calls) == 1, "the token must be collected via getpass.getpass()"
    assert len(input_calls) == 2, "backend URL and watch folder must still use ordinary input()"
    loaded = agent_config.load_config()
    assert loaded.token == "test-agent-token"


def test_setup_rejects_a_blank_token_returned_by_getpass_and_writes_nothing(
    isolated_config_path, monkeypatch, tmp_path
):
    _answer(monkeypatch, "", "   ", str(tmp_path / "watched"))

    with pytest.raises(SystemExit):
        agent_setup.main()

    assert not isolated_config_path.exists()


def test_setup_saves_a_valid_token_entered_via_getpass_and_it_reads_back_unchanged(
    isolated_config_path, monkeypatch, tmp_path
):
    folder = tmp_path / "watched"
    _answer(monkeypatch, "http://example.test", "test-agent-token", str(folder))

    agent_setup.main()

    loaded = agent_config.load_config()
    assert loaded.token == "test-agent-token"


def test_setup_never_prints_the_token(isolated_config_path, monkeypatch, tmp_path, capsys):
    """getpass.getpass() itself is what guarantees no terminal echo while
    typing -- this only checks the layer setup.py controls: it must never
    separately print the token via its own output statements."""
    folder = tmp_path / "watched"
    _answer(monkeypatch, "http://example.test", "test-agent-token", str(folder))

    agent_setup.main()

    captured = capsys.readouterr()
    assert "test-agent-token" not in captured.out
    assert "test-agent-token" not in captured.err
