"""Entry point: `python -m agent.main` from the repo root when running
from source, or the packaged FileFlowAgent.exe when installed. On first
run (no agent/config.json yet) it opens the setup wizard before doing
anything else; after that, the tray icon owns the process's main thread
until "Quit" is chosen, with the watcher and command poller running as
background threads."""

import logging
import os
import sys
import threading
from pathlib import Path

# The agent reuses the backend's own pure helpers (automation/file_ops.py,
# rules/classifier.py, services/*) rather than duplicating them --
# backend/ isn't an installed package, so it has to go on sys.path
# explicitly, exactly the way backend/main.py itself expects to be run
# with backend/ as the import root. The PyInstaller spec adds the same
# directory via `pathex` so this resolves identically in a frozen build.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from agent import outbox, singleton  # noqa: E402
from agent.client import AgentClient  # noqa: E402
from agent.commands import poll_forever  # noqa: E402
from agent.config import AgentConfig, CONFIG_PATH, load_config  # noqa: E402
from agent.setup_gui import run_setup_wizard  # noqa: E402
from agent.tray import run_tray  # noqa: E402
from agent.watcher import start_watching  # noqa: E402
from services.notification_service import notify  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("fileflow.agent")


class AgentRuntime:
    """Owns the live client/observer/poller so the tray icon's
    Pause/Reconfigure/Quit actions have something concrete to act on."""

    def __init__(self, config: AgentConfig):
        self.client = AgentClient(config)
        self.watch_root = config.watch_root
        # One durable local outbox for the whole process's lifetime --
        # reopening the same file on restart picks up any work left
        # over from a previous run (e.g. the process was killed mid-outage).
        self.outbox_conn = outbox.open_queue()
        self.observer, self.handler = start_watching(self.client, self.watch_root, self.outbox_conn)
        # poll_forever() itself loops forever with its own sleep/backoff --
        # daemon=True is enough to have it die with the process on Quit,
        # no separate stop signal needed.
        threading.Thread(
            target=poll_forever,
            args=(self.client, self.watch_root, self.outbox_conn, self.shutdown),
            kwargs={"get_handler": lambda: self.handler},
            daemon=True,
        ).start()
        logger.info("FileFlow agent running -- watching %s", self.watch_root)

    def is_paused(self) -> bool:
        return self.handler.paused

    def toggle_pause(self) -> None:
        # Only the manual half of the pause state -- the remote half is
        # owned by poll_forever's periodic sync (commands.py) and would
        # just get overwritten on the next cycle if toggled here too.
        self.handler.manually_paused = not self.handler.manually_paused
        logger.info("Watching %s", "paused" if self.handler.paused else "resumed")

    def open_folder(self) -> None:
        os.startfile(str(self.watch_root))  # noqa: S606 -- Windows-only by design

    def apply_config(self, config: AgentConfig) -> None:
        """Applies a saved Reconfigure -- new token/backend URL take effect
        immediately on the existing client; a changed watch folder means
        stopping the old Observer and starting a fresh one, since watchdog
        Observers watch one fixed path for their whole lifetime."""
        self.client.reconfigure(config)
        if Path(config.watch_folder).resolve() != self.watch_root.resolve():
            self.observer.stop()
            self.observer.join(timeout=5)
            self.watch_root = config.watch_root
            self.observer, self.handler = start_watching(self.client, self.watch_root, self.outbox_conn)
            logger.info("Reconfigured -- now watching %s", self.watch_root)
        else:
            logger.info("Reconfigured.")

    def shutdown(self) -> None:
        self.observer.stop()
        self.observer.join(timeout=5)
        logger.info("Agent stopped.")


def main() -> None:
    # This app has no window -- launching it a second time (e.g. clicking
    # the Start Menu entry while it's already running in the tray) would
    # otherwise silently start a competing instance with nothing visible
    # to show for it, which looks exactly like "it doesn't work." Bail out
    # loudly instead.
    if not singleton.acquire():
        notify(
            "FileFlow Agent",
            "Already running -- look for its icon near the clock (you may "
            "need to click the small arrow to show hidden icons).",
            {},
        )
        logger.info("Another instance is already running -- exiting.")
        return

    existing_config = load_config() if CONFIG_PATH.exists() else None
    if existing_config is None:
        existing_config = run_setup_wizard()
        if existing_config is None:
            logger.info("Setup cancelled -- exiting.")
            return

    runtime = AgentRuntime(existing_config)
    notify(
        "FileFlow Agent",
        "Running in the background -- look for its icon near the clock (you "
        "may need to click the small arrow to show hidden icons).",
        {},
    )

    def on_reconfigure() -> None:
        current = load_config()
        updated = run_setup_wizard(existing=current)
        if updated is not None:
            runtime.apply_config(updated)

    run_tray(
        is_paused=runtime.is_paused,
        on_toggle_pause=runtime.toggle_pause,
        on_open_folder=runtime.open_folder,
        on_reconfigure=on_reconfigure,
        on_quit=runtime.shutdown,
    )


if __name__ == "__main__":
    main()
