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
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        backend_url, token, watch_folder = data["backend_url"], data["token"], data["watch_folder"]
        # Confirmed real gap: without this check, a non-string value here
        # (only reachable by hand-editing config.json -- both setup.py and
        # setup_gui.py always write real strings) loaded successfully with
        # no error at all, and only failed later, with a raw, uncaught
        # TypeError, the moment something actually used it (e.g.
        # AgentRuntime.__init__ -> start_watching() needing watch_root to
        # be a real path) -- by which point there's no path left to show a
        # clear message. Raising TypeError here routes it through the same
        # friendly SystemExit below as any other corrupted config.
        if not all(isinstance(v, str) for v in (backend_url, token, watch_folder)):
            raise TypeError("backend_url, token, and watch_folder must all be strings")
        return AgentConfig(backend_url=backend_url.rstrip("/"), token=token, watch_folder=watch_folder)
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        # save_config() below isn't an atomic write -- a process kill, a
        # full disk, or a power loss mid-save can leave this file truncated
        # or otherwise invalid. Previously that surfaced as an unhandled
        # JSONDecodeError/KeyError straight out of main(), which for an
        # agent launched silently from Windows Startup (no console
        # attached) meant the process just vanished with nothing to show
        # for it -- no tray icon, no notification, no clue why. Same clear,
        # actionable message as the missing-file case above, instead of a
        # raw traceback nobody sees.
        raise SystemExit(
            f"Agent config at {CONFIG_PATH} is corrupted ({exc}).\n"
            "Run `python -m agent.setup` again (from the repo root) to recreate it."
        ) from exc


def save_config(backend_url: str, token: str, watch_folder: str) -> None:
    CONFIG_PATH.write_text(
        json.dumps(
            {"backend_url": backend_url.rstrip("/"), "token": token, "watch_folder": watch_folder},
            indent=2,
        ),
        encoding="utf-8",
    )
