"""Release-artifact verification -- NOT part of the normal fast unit-test
run. A fresh developer checkout has no release binary in
backend/agent_releases/ at all (only a .gitkeep -- the real .exe is
gitignored and built locally), so asserting it exists unconditionally
would fail on every ordinary `pytest backend/tests` run for every
contributor forever, which defeats the point of a regression test.

This module's tests only run when a human has set
FILEFLOW_VERIFY_RELEASE=1 -- i.e., when actually verifying/publishing a
real release, per the manual checklist in agent/installer/
fileflow_agent.iss's header comment and backend/config/agent_release.py's
own docstring (bump agent/VERSION + AGENT_LATEST_VERSION together,
rebuild, drop the installer into agent_releases/, restart the backend).
In the normal case they're silently skipped, not failed.

Regression context: a real packaging audit found AGENT_LATEST_VERSION
already bumped to "1.0.4" (matching agent/VERSION and
fileflow_agent.iss's AppVersion) while backend/agent_releases/ still only
had "FileFlowAgentSetup-1.0.3.exe" -- the release checklist's final
manual step (build + drop in the new binary) was never completed for that
version bump. That leaves AGENT_RELEASE_PATH pointing at a file that
doesn't exist, so /api/agent/version and /api/agent/download would both
404 for any real agent, and self-update would never actually trigger.
This is exactly the gap these tests exist to catch, the next time it
happens, for whoever runs the release checklist with the env var set.
"""

import os

import pytest

from config.agent_release import AGENT_LATEST_VERSION, AGENT_RELEASE_PATH, agent_release_sha256

pytestmark = pytest.mark.skipif(
    not os.environ.get("FILEFLOW_VERIFY_RELEASE"),
    reason="Release-artifact verification only runs with FILEFLOW_VERIFY_RELEASE=1 set "
    "(e.g. as the last step of actually publishing a release) -- an ordinary developer "
    "checkout has no release binary in backend/agent_releases/, and that's expected.",
)


def test_the_advertised_release_artifact_actually_exists():
    assert AGENT_RELEASE_PATH.exists(), (
        f"AGENT_LATEST_VERSION is {AGENT_LATEST_VERSION!r} but {AGENT_RELEASE_PATH} "
        "does not exist -- the release checklist's final step (build the installer, "
        "copy it into backend/agent_releases/) was not completed for this version."
    )


def test_the_release_artifacts_sha256_can_be_calculated():
    assert len(agent_release_sha256()) == 64
