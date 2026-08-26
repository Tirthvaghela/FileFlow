"""Lightweight, no-external-tool-required regression coverage for the
FileFlow Agent's packaging configuration. Does NOT invoke PyInstaller or
Inno Setup itself (both are slow -- 15-30s+ -- and Inno Setup in
particular is often not installed at all, which would make this suite
unrunnable in most environments). These checks instead protect the
specific, fast-to-verify cross-file consistency invariants a real
packaging audit found worth guarding:

- agent/requirements.txt is the venv the README's documented build
  command (`pyinstaller agent/fileflow_agent.spec --noconfirm`) assumes
  is already set up. python-dotenv was confirmed, via an actual clean
  build + run, to be a genuine runtime dependency missing from that file
  (backend/config/settings.py does `from dotenv import load_dotenv` at
  module level, and it's pulled in transitively by automation.file_ops /
  services.uipath_service, both imported by agent/watcher.py and
  agent/commands.py) -- a FileFlowAgent.exe built from just this file
  crashed immediately with "ModuleNotFoundError: No module named
  'dotenv'", before agent/main.py's own code ever ran. Fixed by adding
  it here; this test guards the fix.
- agent/VERSION, backend/config/agent_release.py's AGENT_LATEST_VERSION,
  and fileflow_agent.iss's AppVersion must all agree -- a real audit
  found the release *binary* itself (backend/agent_releases/) still
  stale at 1.0.3 while all three of these already agreed on 1.0.4, which
  these checks would NOT have caught (that's a missing-artifact problem,
  not a version-string one -- see the audit report) but are still worth
  protecting against the more common drift: someone bumping one without
  the other two.
- The tray icon asset and the built executable's name are referenced
  consistently across the PyInstaller spec and the Inno Setup script.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_agent_requirements_declares_python_dotenv():
    """Regression test for the confirmed bug described in the module
    docstring above."""
    requirements = (REPO_ROOT / "agent" / "requirements.txt").read_text()
    assert re.search(r"^python-dotenv==", requirements, re.MULTILINE)


def test_agent_version_matches_the_backends_advertised_latest_version():
    agent_version = (REPO_ROOT / "agent" / "VERSION").read_text().strip()

    agent_release_source = (REPO_ROOT / "backend" / "config" / "agent_release.py").read_text()
    match = re.search(r'AGENT_LATEST_VERSION\s*=\s*"([^"]+)"', agent_release_source)
    assert match, "AGENT_LATEST_VERSION assignment not found in backend/config/agent_release.py"

    assert agent_version == match.group(1)


def test_installer_script_app_version_matches_agent_version():
    agent_version = (REPO_ROOT / "agent" / "VERSION").read_text().strip()

    iss_source = (REPO_ROOT / "agent" / "installer" / "fileflow_agent.iss").read_text()
    match = re.search(r'#define AppVersion "([^"]+)"', iss_source)
    assert match, "AppVersion #define not found in fileflow_agent.iss"

    assert agent_version == match.group(1)


def test_tray_icon_asset_referenced_by_the_spec_and_installer_actually_exists():
    icon_path = REPO_ROOT / "agent" / "assets" / "icon.ico"
    assert icon_path.is_file()


def test_pyinstaller_and_inno_setup_agree_on_the_built_executable_name():
    """fileflow_agent.spec names both EXE() and COLLECT() "FileFlowAgent"
    (producing dist/FileFlowAgent/FileFlowAgent.exe, confirmed by a real
    build); fileflow_agent.iss references that exact name in
    [Icons]/[Run]/[UninstallRun]/[Code]. Protects against the name
    silently drifting apart in only one of the two files."""
    spec_source = (REPO_ROOT / "agent" / "fileflow_agent.spec").read_text()
    assert 'name="FileFlowAgent"' in spec_source

    iss_source = (REPO_ROOT / "agent" / "installer" / "fileflow_agent.iss").read_text()
    assert "FileFlowAgent.exe" in iss_source


def test_installer_script_dist_dir_points_at_pyinstallers_actual_output_location():
    """fileflow_agent.iss's DistDir is relative to its own directory
    (agent/installer/); confirmed by a real build that PyInstaller's
    default COLLECT output for this spec is <repo_root>/dist/FileFlowAgent."""
    iss_source = (REPO_ROOT / "agent" / "installer" / "fileflow_agent.iss").read_text()
    match = re.search(r'#define DistDir "([^"]+)"', iss_source)
    assert match, "DistDir #define not found in fileflow_agent.iss"

    resolved = (REPO_ROOT / "agent" / "installer" / match.group(1)).resolve()
    assert resolved == (REPO_ROOT / "dist" / "FileFlowAgent")
