import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import uipath_service
from services.uipath_service import execute_move_via_uipath


@pytest.fixture()
def uipath_configured(monkeypatch, tmp_path):
    monkeypatch.setattr(uipath_service.settings, "UIPATH_ENABLED", True)
    monkeypatch.setattr(uipath_service.settings, "UIPATH_ROBOT_EXE", tmp_path / "UiRobot.exe")
    monkeypatch.setattr(uipath_service.settings, "UIPATH_PACKAGE_PATH", tmp_path / "FileFlowMove.nupkg")
    monkeypatch.setattr(uipath_service.settings, "UIPATH_ENTRY_POINT", "MoveFile.xaml")
    monkeypatch.setattr(uipath_service.settings, "UIPATH_TIMEOUT_SECONDS", 30)


def _completed(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class TestExecuteMoveViaUiPath:
    def test_returns_none_when_disabled(self, monkeypatch, tmp_path):
        monkeypatch.setattr(uipath_service.settings, "UIPATH_ENABLED", False)
        calls = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append(a) or _completed())

        result = execute_move_via_uipath(tmp_path / "a.txt", tmp_path / "dest", "a.txt")

        assert result is None
        assert calls == []  # never even tries to shell out

    def test_returns_none_when_enabled_but_not_configured(self, monkeypatch, tmp_path):
        monkeypatch.setattr(uipath_service.settings, "UIPATH_ENABLED", True)
        monkeypatch.setattr(uipath_service.settings, "UIPATH_ROBOT_EXE", None)
        monkeypatch.setattr(uipath_service.settings, "UIPATH_PACKAGE_PATH", None)

        result = execute_move_via_uipath(tmp_path / "a.txt", tmp_path / "dest", "a.txt")

        assert result is None

    def test_returns_the_destination_path_on_success(self, uipath_configured, monkeypatch, tmp_path):
        dest = tmp_path / "dest" / "a.txt"
        dest.parent.mkdir()
        dest.write_text("moved by uipath")  # the real move already happened
        monkeypatch.setattr(
            subprocess, "run", lambda *a, **kw: _completed(stdout=json.dumps({"out_DestinationPath": str(dest)}))
        )

        result = execute_move_via_uipath(tmp_path / "a.txt", dest.parent, "a.txt")

        assert result == dest

    def test_sends_the_expected_arguments_to_uirobot(self, uipath_configured, monkeypatch, tmp_path):
        dest = tmp_path / "dest" / "a.txt"
        dest.parent.mkdir()
        dest.write_text("hi")
        captured = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            return _completed(stdout=json.dumps({"out_DestinationPath": str(dest)}))

        monkeypatch.setattr(subprocess, "run", fake_run)
        source = tmp_path / "a.txt"

        execute_move_via_uipath(source, dest.parent, "a.txt")

        args = captured["args"]
        assert args[0] == str(uipath_service.settings.UIPATH_ROBOT_EXE)
        assert args[1] == "execute"
        assert "--entry" in args and args[args.index("--entry") + 1] == "MoveFile.xaml"
        input_json = json.loads(args[args.index("--input") + 1])
        assert input_json == {
            "in_SourceFilePath": str(source),
            "in_DestFolderPath": str(dest.parent),
            "in_FinalFileName": "a.txt",
        }

    def test_returns_none_when_uirobot_exits_nonzero(self, uipath_configured, monkeypatch, tmp_path):
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _completed(returncode=1, stderr="boom"))

        result = execute_move_via_uipath(tmp_path / "a.txt", tmp_path / "dest", "a.txt")

        assert result is None

    def test_returns_none_for_unparseable_output(self, uipath_configured, monkeypatch, tmp_path):
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _completed(stdout="not json"))

        result = execute_move_via_uipath(tmp_path / "a.txt", tmp_path / "dest", "a.txt")

        assert result is None

    def test_returns_none_when_reported_destination_does_not_exist(
        self, uipath_configured, monkeypatch, tmp_path
    ):
        # UiRobot claims success but the file genuinely isn't there --
        # never trust the report over the filesystem.
        never_created = tmp_path / "dest" / "phantom.txt"
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: _completed(stdout=json.dumps({"out_DestinationPath": str(never_created)})),
        )

        result = execute_move_via_uipath(tmp_path / "a.txt", tmp_path / "dest", "phantom.txt")

        assert result is None

    def test_returns_none_when_the_robot_executable_cannot_be_launched(
        self, uipath_configured, monkeypatch, tmp_path
    ):
        def raise_not_found(*a, **kw):
            raise FileNotFoundError("UiRobot.exe not found")

        monkeypatch.setattr(subprocess, "run", raise_not_found)

        result = execute_move_via_uipath(tmp_path / "a.txt", tmp_path / "dest", "a.txt")

        assert result is None

    def test_returns_none_on_timeout(self, uipath_configured, monkeypatch, tmp_path):
        def raise_timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="UiRobot.exe", timeout=30)

        monkeypatch.setattr(subprocess, "run", raise_timeout)

        result = execute_move_via_uipath(tmp_path / "a.txt", tmp_path / "dest", "a.txt")

        assert result is None
