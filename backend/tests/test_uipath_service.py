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

    def test_special_characters_in_the_path_reach_the_robot_unmangled(
        self, uipath_configured, monkeypatch, tmp_path
    ):
        """subprocess.run() is called with an argument LIST here, never
        shell=True (confirmed by reading the call) -- so there is no shell
        metacharacter interpretation to worry about, only whether the raw
        path survives unmangled into the JSON payload. A filename with
        spaces, parentheses, an ampersand, and a semicolon exercises
        exactly the characters a shell-based command construction would
        have needed to escape."""
        tricky_name = "Report (final) & notes; v2.txt"
        dest_folder = tmp_path / "dest folder (2024)"
        dest_folder.mkdir()
        dest = dest_folder / tricky_name
        dest.write_text("hi")
        captured = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return _completed(stdout=json.dumps({"out_DestinationPath": str(dest)}))

        monkeypatch.setattr(subprocess, "run", fake_run)
        source = tmp_path / tricky_name

        result = execute_move_via_uipath(source, dest_folder, tricky_name)

        assert result == dest
        assert "shell" not in captured["kwargs"] or captured["kwargs"]["shell"] is False
        input_json = json.loads(captured["args"][captured["args"].index("--input") + 1])
        assert input_json["in_SourceFilePath"] == str(source)
        assert input_json["in_DestFolderPath"] == str(dest_folder)
        assert input_json["in_FinalFileName"] == tricky_name

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

    def test_returns_none_when_reported_destination_is_outside_the_requested_folder(
        self, uipath_configured, monkeypatch, tmp_path
    ):
        """Regression test for a real, confirmed gap: execute_move_via_
        uipath() only ever checked that *something* exists at whatever
        out_DestinationPath the Robot's stdout reported -- never that this
        matches the dest_folder/final_name it was actually asked to use.
        The real, unmodified MoveFile.xaml always computes out_
        DestinationPath as exactly Combine(in_DestFolderPath, in_
        FinalFileName) (confirmed by reading the workflow source), so this
        never fires in normal operation -- but nothing enforced it, and
        process_file()'s own caller discards this function's return value
        entirely once it's non-None, logging its OWN pre-computed
        dest_path unconditionally. A Robot (or a differently-built
        package pointed at by a misconfigured UIPATH_PACKAGE_PATH, or a
        compromised workflow) reporting an unrelated-but-existing path
        would previously be trusted completely, with no verification it
        has anything to do with the requested folder at all."""
        requested_dest_folder = tmp_path / "dest"
        requested_dest_folder.mkdir()
        # A real, pre-existing file that has nothing to do with this move --
        # simulating a Robot response that reports success against some
        # other path entirely.
        unrelated_existing_file = tmp_path / "unrelated_preexisting_file.txt"
        unrelated_existing_file.write_text("not the file this call was about")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: _completed(
                stdout=json.dumps({"out_DestinationPath": str(unrelated_existing_file)})
            ),
        )

        result = execute_move_via_uipath(tmp_path / "a.txt", requested_dest_folder, "a.txt")

        assert result is None, (
            "a reported destination outside the requested dest_folder/final_name must be "
            "rejected, not trusted just because something happens to exist there"
        )

    def test_accepts_the_reported_destination_when_it_exactly_matches_the_request(
        self, uipath_configured, monkeypatch, tmp_path
    ):
        """Non-regression companion to the test above -- confirms the fix
        doesn't also reject the normal, correct case."""
        dest_folder = tmp_path / "dest"
        dest_folder.mkdir()
        expected_dest = dest_folder / "a.txt"
        expected_dest.write_text("moved by uipath")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: _completed(
                stdout=json.dumps({"out_DestinationPath": str(expected_dest)})
            ),
        )

        result = execute_move_via_uipath(tmp_path / "a.txt", dest_folder, "a.txt")

        assert result == expected_dest
