import hashlib

import pytest
import requests

from agent import updater
from agent.version import AGENT_VERSION


def test_parse_version_orders_correctly():
    assert updater._parse_version("1.2.10") > updater._parse_version("1.2.9")
    assert updater._parse_version("2.0.0") > updater._parse_version("1.99.99")
    assert updater._parse_version("1.0.0") == updater._parse_version("1.0.0")


class _ManifestClient:
    def __init__(self, version):
        self._version = version

    def get_latest_version(self):
        return {"version": self._version, "sha256": "irrelevant", "download_url": "/x"}


class _OfflineClient:
    def get_latest_version(self):
        raise requests.exceptions.ConnectionError("offline")


def test_check_for_update_returns_none_for_the_same_version():
    assert updater.check_for_update(_ManifestClient(AGENT_VERSION)) is None


def test_check_for_update_returns_none_for_an_older_version():
    assert updater.check_for_update(_ManifestClient("0.0.1")) is None


def test_check_for_update_returns_the_manifest_for_a_newer_version():
    major, minor, patch = updater._parse_version(AGENT_VERSION)
    newer = f"{major}.{minor}.{patch + 1}"
    result = updater.check_for_update(_ManifestClient(newer))
    assert result == {"version": newer, "sha256": "irrelevant", "download_url": "/x"}


def test_check_for_update_tolerates_a_connection_failure():
    assert updater.check_for_update(_OfflineClient()) is None


class _DownloadClient:
    def __init__(self, data, fail=False):
        self._data = data
        self._fail = fail

    def download_installer(self):
        if self._fail:
            raise requests.exceptions.ConnectionError("offline")
        return self._data


def test_download_and_apply_rejects_checksum_mismatch(monkeypatch):
    launched = []
    monkeypatch.setattr(
        updater.subprocess, "Popen", lambda *a, **k: launched.append((a, k))
    )
    data = b"totally real installer"
    manifest = {"version": "9.9.9", "sha256": "not-the-real-hash"}

    result = updater.download_and_apply(_DownloadClient(data), manifest)

    assert result is False
    assert launched == []


def test_download_and_apply_launches_on_checksum_match(monkeypatch, tmp_path):
    launched = []
    monkeypatch.setattr(
        updater.subprocess, "Popen", lambda *a, **k: launched.append((a, k))
    )
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    data = b"totally real installer"
    manifest = {"version": "9.9.9", "sha256": hashlib.sha256(data).hexdigest()}

    result = updater.download_and_apply(_DownloadClient(data), manifest)

    assert result is True
    assert len(launched) == 1
    args, kwargs = launched[0]
    installer_path = args[0][0]
    assert installer_path.endswith("FileFlowAgentSetup-9.9.9.exe")
    assert "/VERYSILENT" in args[0]


def test_download_and_apply_does_not_launch_on_download_failure(monkeypatch):
    launched = []
    monkeypatch.setattr(
        updater.subprocess, "Popen", lambda *a, **k: launched.append((a, k))
    )
    result = updater.download_and_apply(
        _DownloadClient(b"", fail=True), {"version": "9.9.9", "sha256": "x"}
    )
    assert result is False
    assert launched == []
