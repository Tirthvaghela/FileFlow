import pytest

from agent import config


def test_loads_a_valid_config(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        '{"backend_url": "http://localhost:8000/", "token": "t", "watch_folder": "C:\\\\Downloads"}'
    )
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    loaded = config.load_config()

    assert loaded.backend_url == "http://localhost:8000"  # trailing slash stripped
    assert loaded.token == "t"
    assert loaded.watch_folder == "C:\\Downloads"


def test_missing_file_raises_a_clear_system_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "does_not_exist.json")

    with pytest.raises(SystemExit):
        config.load_config()


def test_malformed_json_raises_a_clear_system_exit_not_a_raw_traceback(tmp_path, monkeypatch):
    """save_config() isn't an atomic write -- a killed process, a full
    disk, or a power loss mid-save can leave this file truncated. Previously
    this surfaced as an unhandled JSONDecodeError straight out of load_config(),
    which for an agent launched silently from Windows Startup (no console
    attached) meant it just vanished with no error visible anywhere."""
    path = tmp_path / "config.json"
    path.write_text("{not valid json")
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    with pytest.raises(SystemExit, match="corrupted"):
        config.load_config()


def test_missing_required_key_raises_a_clear_system_exit(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"backend_url": "http://localhost:8000", "token": "t"}')  # no watch_folder
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    with pytest.raises(SystemExit, match="corrupted"):
        config.load_config()


def test_empty_file_raises_a_clear_system_exit_not_a_raw_traceback(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text("")  # a write interrupted at the very start
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    with pytest.raises(SystemExit, match="corrupted"):
        config.load_config()


def test_wrong_typed_watch_folder_raises_a_clear_system_exit_not_a_later_crash(tmp_path, monkeypatch):
    """Regression test for a real, confirmed gap: load_config() only ever
    checked that the three keys exist, not that their values are the
    strings AgentConfig assumes. A non-string watch_folder (only reachable
    by hand-editing config.json directly -- both setup.py and
    setup_gui.py always write real strings) previously loaded
    successfully with no error at all, and only failed later -- with a
    raw, uncaught TypeError instead of a friendly SystemExit -- the
    moment something actually accessed .watch_root (e.g.
    AgentRuntime.__init__ -> start_watching()), by which point main()
    has no path left to show a clear message. Exactly the same "silent
    death, no console, no tray, no clue why" failure mode this file's
    corrupted-JSON handling already exists to prevent -- just not
    reaching this specific case before this fix."""
    path = tmp_path / "config.json"
    path.write_text('{"backend_url": "http://localhost:8000", "token": "t", "watch_folder": 12345}')
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    with pytest.raises(SystemExit, match="corrupted"):
        config.load_config()


def test_wrong_typed_token_raises_a_clear_system_exit(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"backend_url": "http://localhost:8000", "token": null, "watch_folder": "C:\\\\W"}')
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    with pytest.raises(SystemExit, match="corrupted"):
        config.load_config()


def test_extra_unknown_fields_are_silently_ignored(tmp_path, monkeypatch):
    """Not a bug: load_config() only ever reads the three keys it knows
    about by name (never **data), so an older or newer config.json
    carrying extra fields loads exactly the same as one without them --
    already backward- and forward-compatible for this case with no
    migration code needed."""
    path = tmp_path / "config.json"
    path.write_text(
        '{"backend_url": "http://localhost:8000", "token": "t", "watch_folder": "C:\\\\W", '
        '"future_field": "something a newer version might add"}'
    )
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    loaded = config.load_config()

    assert loaded == config.AgentConfig(
        backend_url="http://localhost:8000", token="t", watch_folder="C:\\W"
    )
