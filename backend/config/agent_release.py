"""Where the backend finds the latest agent installer, and what version
it claims to be. Bumped by hand as part of the (manual, no-CI) release
checklist in agent/installer/fileflow_agent.iss's header comment:
1. bump agent/VERSION and this file's AGENT_LATEST_VERSION together
2. rebuild (pyinstaller, then iscc)
3. drop the resulting installer into agent_releases/ under the name below
4. restart the backend so it picks up the new constants."""

from functools import lru_cache
from hashlib import sha256
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
AGENT_RELEASES_DIR = BACKEND_DIR / "agent_releases"

AGENT_LATEST_VERSION = "1.0.4"
AGENT_RELEASE_PATH = AGENT_RELEASES_DIR / f"FileFlowAgentSetup-{AGENT_LATEST_VERSION}.exe"


@lru_cache(maxsize=1)
def agent_release_sha256() -> str:
    """Cached for the process's lifetime -- the release file doesn't
    change while the server is running; publishing a new one already
    requires a restart to pick up the new AGENT_LATEST_VERSION anyway."""
    return sha256(AGENT_RELEASE_PATH.read_bytes()).hexdigest()
