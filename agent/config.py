"""Local agent configuration -- one backend URL, one long-lived agent
token (from Settings -> "Generate agent token" in the web dashboard), and
one real local folder to watch. Deliberately just a JSON file next to the
script for now; a proper installer (Phase 3) will replace this with
something that lives in the OS's real per-user app-data directory."""

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


@dataclass
class AgentConfig:
    backend_url: str
    token: str
    watch_folder: str

    @property
    def watch_root(self) -> Path:
        return Path(self.watch_folder)


def load_config() -> AgentConfig:
    if not CONFIG_PATH.exists():
        raise SystemExit(
            f"No agent config found at {CONFIG_PATH}.\n"
            "Run `python -m agent.setup` first (from the repo root)."
        )
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return AgentConfig(
        backend_url=data["backend_url"].rstrip("/"),
        token=data["token"],
        watch_folder=data["watch_folder"],
    )


def save_config(backend_url: str, token: str, watch_folder: str) -> None:
    CONFIG_PATH.write_text(
        json.dumps(
            {"backend_url": backend_url.rstrip("/"), "token": token, "watch_folder": watch_folder},
            indent=2,
        ),
        encoding="utf-8",
    )
