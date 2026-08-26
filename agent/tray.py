"""System tray icon (pystray) -- visible, always-there proof the agent is
running, plus quick access to pause/reconfigure/quit without a terminal
window. Runs on the main thread; the watcher Observer and command poller
are the background threads instead (the reverse of running from source,
where nothing needed a tray icon at all)."""

import logging
from pathlib import Path

import pystray
from PIL import Image

logger = logging.getLogger("fileflow.agent.tray")

ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.ico"


def run_tray(*, is_paused, on_toggle_pause, on_open_folder, on_reconfigure, on_quit) -> None:
    """Blocks until "Quit" is chosen. `is_paused` is re-checked by pystray
    every time the menu is opened (it's a live lambda, not a snapshot), so
    the checkbox always reflects the current state.

    Every callback below is wrapped in its own try/except: pystray's win32
    backend dispatches a menu click with nothing but a bare `except:`
    around its whole message loop, which on catching *anything* tears the
    entire tray icon down and returns from icon.run() -- ending run_tray()
    and, since every other agent thread (the watcher Observer, the command
    poller) is a daemon thread, silently ending the whole process. A
    realistic, reachable failure -- a bad Reconfigure attempt (apply_config
    re-raises even after its own internal rollback) or Open Folder on a
    deleted watch folder -- would otherwise kill the running agent with no
    visible trace beyond one line from pystray's own logger, which in the
    real windowless packaged build goes nowhere anyone would see it.
    Deliberately `except Exception`, not a bare `except:` -- this must not
    swallow a SystemExit like the one agent/config.py's load_config()
    intentionally raises when config.json is missing/corrupted."""
    image = Image.open(ICON_PATH)

    def _toggle_pause(icon, item):
        try:
            on_toggle_pause()
        except Exception:
            logger.exception("Tray: pause/resume failed")

    def _open_folder(icon, item):
        try:
            on_open_folder()
        except Exception:
            logger.exception("Tray: open folder failed")

    def _reconfigure(icon, item):
        try:
            on_reconfigure()
        except Exception:
            logger.exception("Tray: reconfigure failed")

    def _quit(icon, item):
        try:
            on_quit()
        except Exception:
            logger.exception("Tray: shutdown failed")
        finally:
            # The user asked to quit -- the icon must disappear even if
            # shutdown() itself hit an internal error.
            icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open watched folder", _open_folder),
        pystray.MenuItem("Pause watching", _toggle_pause, checked=lambda item: is_paused()),
        pystray.MenuItem("Reconfigure...", _reconfigure),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit FileFlow Agent", _quit),
    )
    icon = pystray.Icon("FileFlow Agent", image, "FileFlow Agent", menu)
    icon.run()
