"""One-time interactive setup: `python -m agent.setup` from the repo root.
Packaging this into a real installer step is Phase 3 -- for now it just
writes agent/config.json."""

from agent.config import CONFIG_PATH, save_config


def main() -> None:
    print("FileFlow Agent setup\n")
    backend_url = input("Backend URL [http://localhost:8000]: ").strip() or "http://localhost:8000"
    token = input("Agent token (Settings -> Generate agent token): ").strip()
    watch_folder = input("Folder on this machine for the agent to watch: ").strip()

    if not token:
        raise SystemExit("An agent token is required.")
    if not watch_folder:
        raise SystemExit("A watch folder is required.")

    save_config(backend_url, token, watch_folder)
    print(f"\nSaved config to {CONFIG_PATH}")
    print("Start the agent with: python -m agent.main")


if __name__ == "__main__":
    main()
