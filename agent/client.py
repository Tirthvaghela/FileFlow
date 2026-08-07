"""Thin wrapper around the backend's /api/agent/* endpoints."""

import requests

from agent.config import AgentConfig


class AgentClient:
    def __init__(self, config: AgentConfig, timeout: float = 10.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.reconfigure(config)

    def reconfigure(self, config: AgentConfig) -> None:
        """Applies a new backend URL / token in place -- used when the tray
        icon's "Reconfigure" saves changes, so a full app restart isn't
        needed just to pick up a new token."""
        self.base_url = config.backend_url
        self.session.headers["Authorization"] = f"Bearer {config.token}"

    def get_rules(self) -> dict:
        resp = self.session.get(f"{self.base_url}/api/agent/rules", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def report_activity(self, **fields) -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/agent/activity", json=fields, timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    def get_commands(self) -> list[dict]:
        resp = self.session.get(f"{self.base_url}/api/agent/commands", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def complete_command(
        self, command_id: int, success: bool, error: str | None = None, result: dict | None = None
    ) -> None:
        resp = self.session.post(
            f"{self.base_url}/api/agent/commands/{command_id}/complete",
            json={"success": success, "error": error, "result": result or {}},
            timeout=self.timeout,
        )
        resp.raise_for_status()

    def get_latest_version(self) -> dict:
        resp = self.session.get(f"{self.base_url}/api/agent/version", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def download_installer(self) -> bytes:
        # A real installer is tens of MB -- the default timeout (tuned for
        # tiny JSON calls everywhere else in this client) would be too
        # short for a slow connection to reliably finish the download.
        resp = self.session.get(f"{self.base_url}/api/agent/download", timeout=60.0)
        resp.raise_for_status()
        return resp.content
