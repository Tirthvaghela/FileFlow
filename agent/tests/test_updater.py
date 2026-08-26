import hashlib
from pathlib import Path

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


# ---------------------------------------------------------------------------
# Everything below fills gaps a fresh audit found in the coverage above:
# malformed/missing metadata (section 12/13), a version string crafted for
# path traversal (section 11), an HTTP error response distinct from a bare
# connection failure, an empty/truncated download, and the write/launch
# failure boundaries (sections 8/9) that updater.py leaves for its caller
# (commands.py::poll_forever(), see test_commands.py) to catch -- traced
# and documented as the real, existing contract, not "fixed" here.
# ---------------------------------------------------------------------------


def test_check_for_update_rejects_a_manifest_missing_the_version_key():
    class _NoVersionClient:
        def get_latest_version(self):
            return {"sha256": "irrelevant"}

    assert updater.check_for_update(_NoVersionClient()) is None


def test_check_for_update_rejects_a_non_dict_manifest():
    """client.get_latest_version() is only ever assumed to return a dict --
    confirm a genuinely malformed response (None, a bare list) is handled
    by the same defensive except clause as a missing/bad version, rather
    than raising out of check_for_update() itself."""

    class _WeirdClient:
        def __init__(self, manifest):
            self._manifest = manifest

        def get_latest_version(self):
            return self._manifest

    assert updater.check_for_update(_WeirdClient(None)) is None
    assert updater.check_for_update(_WeirdClient(["not", "a", "dict"])) is None


def test_check_for_update_rejects_a_manifest_with_a_path_traversal_like_version():
    """The real security-relevant gate for section 11: download_and_apply()
    later builds a filename directly from manifest["version"] with no
    separate sanitization step. check_for_update() is what actually keeps
    a hostile/malformed version string from ever reaching that f-string --
    _parse_version() requires every dot-separated component to be a plain
    integer, so a traversal-shaped string can never pass through here."""
    malicious = "..\\..\\..\\Windows\\System32\\evil"
    assert updater.check_for_update(_ManifestClient(malicious)) is None


def test_parse_version_rejects_non_numeric_and_path_like_strings():
    for bad in ["..\\..\\..\\Windows\\System32\\evil", "../../etc/passwd", "1.2.x", ""]:
        with pytest.raises(ValueError):
            updater._parse_version(bad)


def test_download_and_apply_rejects_a_manifest_with_no_sha256_field(monkeypatch):
    """Section 13's explicit requirement: a missing integrity value must
    never silently disable verification. manifest.get("sha256") returns
    None here, and a real hex digest can never equal None, so the mismatch
    check fails closed exactly like a wrong hash would."""
    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *a, **k: launched.append((a, k)))
    data = b"totally real installer"
    manifest = {"version": "9.9.9"}  # no "sha256" key at all

    result = updater.download_and_apply(_DownloadClient(data), manifest)

    assert result is False
    assert launched == []


def test_download_and_apply_rejects_an_empty_downloaded_payload(monkeypatch):
    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *a, **k: launched.append((a, k)))
    manifest = {"version": "9.9.9", "sha256": hashlib.sha256(b"the real installer bytes").hexdigest()}

    result = updater.download_and_apply(_DownloadClient(b""), manifest)

    assert result is False
    assert launched == []


def test_download_and_apply_rejects_a_truncated_download(monkeypatch):
    """No separate "streaming boundary" exists in the current implementation
    -- client.download_installer() returns the complete response body in
    one call, or raises. A response that completes "successfully" but
    truncated (a server bug, a proxy that cuts the body short) can only
    ever manifest here as bytes that don't match the expected hash --
    exactly the same safety net as an outright checksum mismatch, not a
    separate code path."""
    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *a, **k: launched.append((a, k)))
    full_installer = b"the complete real installer payload, all of it"
    manifest = {"version": "9.9.9", "sha256": hashlib.sha256(full_installer).hexdigest()}
    truncated = full_installer[:10]

    result = updater.download_and_apply(_DownloadClient(truncated), manifest)

    assert result is False
    assert launched == []


def test_download_and_apply_does_not_launch_on_an_http_error_response(monkeypatch):
    """Distinct from the existing connection-failure test: raise_for_status()
    raising requests.exceptions.HTTPError (a 404/500 from the backend) is a
    different RequestException subclass -- confirm it's caught by the same
    handler, not just ConnectionError."""
    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *a, **k: launched.append((a, k)))

    class _HttpErrorClient:
        def download_installer(self):
            raise requests.exceptions.HTTPError("500 Server Error")

    result = updater.download_and_apply(_HttpErrorClient(), {"version": "9.9.9", "sha256": "x"})

    assert result is False
    assert launched == []


def test_download_and_apply_propagates_a_write_failure_without_launching(monkeypatch, tmp_path):
    """download_and_apply() has no try/except of its own around
    installer_path.write_bytes() -- traced in the audit as relying on its
    only real caller, commands.py::poll_forever()'s broad exception
    handler, as the actual safety net (see test_commands.py's poll_forever
    tests, which prove that net holds). Documented here as the real,
    existing contract: a write failure propagates out of this function
    rather than being swallowed into a False return."""
    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *a, **k: launched.append((a, k)))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))

    def _fail_write(self, data):
        raise OSError("simulated disk-full while writing the installer")

    monkeypatch.setattr(Path, "write_bytes", _fail_write)
    data = b"totally real installer"
    manifest = {"version": "9.9.9", "sha256": hashlib.sha256(data).hexdigest()}

    with pytest.raises(OSError):
        updater.download_and_apply(_DownloadClient(data), manifest)

    assert launched == [], "must not launch the installer if it couldn't even be written"


def test_download_and_apply_propagates_a_launch_failure_without_returning_true(monkeypatch, tmp_path):
    """Mirrors the write-failure case above: no try/except around
    subprocess.Popen() either. The installer IS fully written to the temp
    dir before this point -- confirmed below -- but a launch failure must
    not be reported as a successful update (a True return is what
    poll_forever() treats as "safe to terminate the agent now")."""
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))

    def _fail_launch(*a, **k):
        raise OSError("simulated: installer executable could not be launched")

    monkeypatch.setattr(updater.subprocess, "Popen", _fail_launch)
    data = b"totally real installer"
    manifest = {"version": "9.9.9", "sha256": hashlib.sha256(data).hexdigest()}

    with pytest.raises(OSError):
        updater.download_and_apply(_DownloadClient(data), manifest)

    assert list(tmp_path.glob("FileFlowAgentSetup-9.9.9.exe")), "the installer must have actually been written"


def test_download_and_apply_cannot_write_outside_the_temp_directory_via_a_malicious_version(
    monkeypatch, tmp_path
):
    """check_for_update()'s _parse_version() gate already guarantees only a
    dot-separated-integers version string ever reaches download_and_apply()
    in the real flow (see the path-traversal tests above) -- this confirms
    a second, independent layer: even calling download_and_apply() directly
    with a manifest carrying a maliciously crafted "version" field (as if
    that gate didn't exist) still can't write outside the intended temp
    directory. Empirically confirmed on this machine: Windows refuses to
    write through a path segment that doesn't already exist on disk, and
    the fixed "FileFlowAgentSetup-" prefix guarantees the first such
    segment is never a bare ".." or a drive root -- so write_bytes() fails
    safely instead of traversing."""
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    data = b"payload"
    malicious_version = "..\\..\\..\\Windows\\System32\\evil"
    manifest = {"version": malicious_version, "sha256": hashlib.sha256(data).hexdigest()}

    with pytest.raises(OSError):
        updater.download_and_apply(_DownloadClient(data), manifest)

    assert list(tmp_path.rglob("evil*")) == [], "nothing must have been written outside the temp dir"
