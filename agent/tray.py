"""System tray icon (pystray) -- visible, always-there proof the agent is
running, plus quick access to pause/reconfigure/quit without a terminal
window. Runs on the main thread; the watcher Observer and command poller
are the background threads instead (the reverse of running from source,
where nothing needed a tray icon at all)."""

from pathlib import Path

import pystray
from PIL import Image

ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.ico"


def run_tray(*, is_paused, on_toggle_pause, on_open_folder, on_reconfigure, on_quit) -> None:
    """Blocks until "Quit" is chosen. `is_paused` is re-checked by pystray
    every time the menu is opened (it's a live lambda, not a snapshot), so
    the checkbox always reflects the current state."""
    image = Image.open(ICON_PATH)

    def _toggle_pause(icon, item):
        on_toggle_pause()

    def _open_folder(icon, item):
        on_open_folder()

    def _reconfigure(icon, item):
        on_reconfigure()

    def _quit(icon, item):
        on_quit()
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
