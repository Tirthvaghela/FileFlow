"""One-time interactive setup: `python -m agent.setup` from the repo root.
Packaging this into a real installer step is Phase 3 -- for now it just
writes agent/config.json."""

import getpass
from pathlib import Path

from agent.config import CONFIG_PATH, save_config


def main() -> None:
    print("FileFlow Agent setup\n")
    backend_url = input("Backend URL [http://localhost:8000]: ").strip() or "http://localhost:8000"
    # getpass.getpass() instead of input() so the token isn't echoed to the
    # terminal while typed -- setup_gui.py's equivalent field already masks
    # it the same way (show="*").
    token = getpass.getpass("Agent token (Settings -> Generate agent token): ").strip()
    watch_folder = input("Folder on this machine for the agent to watch: ").strip()

    if not token:
        raise SystemExit("An agent token is required.")
    if not watch_folder:
        raise SystemExit("A watch folder is required.")

    # Resolve to an absolute path before persisting. A relative value (e.g.
    # "Downloads") is only meaningful relative to whatever directory this
    # setup script happened to be run from -- but the agent later
    # interprets that same string relative to whatever directory
    # `python -m agent.main` happens to be launched from instead (Windows
    # Startup, a shortcut with a different "Start in" folder, ...), which
    # isn't guaranteed to match. Unresolved, that silently points the
    # running agent at an entirely different folder than the one actually
    # chosen here. Same reasoning backend/config/settings.py's own
    # resolve_watch_folder() already applies to the web app's equivalent
    # "pick a watch folder" flow.
    watch_folder = str(Path(watch_folder).expanduser().resolve())

    save_config(backend_url, token, watch_folder)
    print(f"\nSaved config to {CONFIG_PATH}")
    print("Start the agent with: python -m agent.main")


if __name__ == "__main__":
    main()
