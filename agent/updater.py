"""Checks the backend for a newer agent release and applies it. Reuses
the same Inno Setup installer this app was built with -- silent-mode
install already does everything a from-scratch in-place file replace
would have to reimplement (overwrite files, keep shortcuts, relaunch),
and it's the exact same path already proven by every manual install/
uninstall in this project."""

import hashlib
import logging
import subprocess
import tempfile
from pathlib import Path

import requests

from agent.version import AGENT_VERSION

logger = logging.getLogger("fileflow.agent.updater")


def _parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


def check_for_update(client) -> dict | None:
    """Returns the version manifest if the backend is advertising
    something newer than this build, else None. Tolerates the backend
    being unreachable or having no release published -- an update check
    failing is never a reason to disrupt anything else the agent does."""
    try:
        manifest = client.get_latest_version()
    except requests.exceptions.RequestException:
        return None
    try:
        if _parse_version(manifest["version"]) > _parse_version(AGENT_VERSION):
            return manifest
    except (KeyError, ValueError, TypeError, AttributeError):
        # AttributeError specifically: manifest["version"] existing but
        # not being a string (an int, None, a list -- JSON shapes the
        # current backend's `version: str` schema can't produce, but a
        # realistic one under agent/backend version skew) makes
        # _parse_version()'s v.split(".") raise this instead of the
        # ValueError/TypeError a malformed *string* version or a missing
        # key already produce -- must be treated the same way as those,
        # not left to crash this function.
        logger.warning("Malformed version manifest from backend: %s", manifest)
    return None


def download_and_apply(client, manifest: dict) -> bool:
    """Downloads the new installer, verifies its checksum, and launches it
    silently and detached. Returns True only once the installer process
    has actually been launched -- the caller must then shut this process
    down promptly, since the installer can't overwrite files this process
    still has open."""
    try:
        data = client.download_installer()
    except requests.exceptions.RequestException:
        logger.warning("Update download failed -- will retry on the next check.")
        return False

    digest = hashlib.sha256(data).hexdigest()
    if digest != manifest.get("sha256"):
        logger.error(
            "Downloaded installer checksum mismatch (expected %s, got %s) -- aborting update.",
            manifest.get("sha256"), digest,
        )
        return False

    installer_path = Path(tempfile.gettempdir()) / f"FileFlowAgentSetup-{manifest['version']}.exe"
    installer_path.write_bytes(data)

    logger.info("Launching update to version %s", manifest["version"])
    subprocess.Popen(
        [str(installer_path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        close_fds=True,
    )
    return True
