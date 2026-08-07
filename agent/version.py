"""Single source of truth for the agent's own version -- kept in a plain
text file rather than hardcoded here so the installer's release
checklist has one obvious file to bump (see agent/installer/fileflow_agent.iss,
which keeps its own AppVersion in manual sync with this)."""

from pathlib import Path

AGENT_VERSION = (Path(__file__).resolve().parent / "VERSION").read_text().strip()
