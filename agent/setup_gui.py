"""GUI setup wizard -- replaces agent/setup.py's console input() prompts,
which don't exist for someone who just double-clicked an .exe with no
terminal attached. Shown on first run (no agent/config.json yet) and
again from the tray icon's "Reconfigure" option."""

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

from agent.config import AgentConfig, save_config

DEFAULT_BACKEND_URL = "http://localhost:8000"
# The web app's Settings page (where "Generate agent token" lives) runs on
# a different origin than the API the agent itself talks to -- this is
# the frontend's default local dev port. Convenience only: if it doesn't
# match a real deployment's actual frontend address, the user can still
# open it themselves.
SETTINGS_PAGE_URL = "http://localhost:5173/app/settings"

ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.ico"


def run_setup_wizard(existing: AgentConfig | None = None) -> AgentConfig | None:
    """Blocks until the user saves or closes the window. Returns the saved
    config, or None if closed without saving."""
    saved: dict = {}

    root = tk.Tk()
    root.title("FileFlow Agent Setup")
    root.resizable(False, False)
    try:
        root.iconbitmap(str(ICON_PATH))
    except Exception:
        pass

    pad = {"padx": 16, "pady": (6, 0)}

    tk.Label(root, text="FileFlow Agent Setup", font=("Segoe UI", 13, "bold")).grid(
        row=0, column=0, columnspan=2, padx=16, pady=(16, 4), sticky="w"
    )
    tk.Label(
        root,
        text="This connects the agent on this computer to your FileFlow account.",
        font=("Segoe UI", 9),
        fg="#555555",
    ).grid(row=1, column=0, columnspan=2, padx=16, sticky="w")

    tk.Label(root, text="Backend URL").grid(row=2, column=0, **pad, sticky="w")
    backend_var = tk.StringVar(value=(existing.backend_url if existing else DEFAULT_BACKEND_URL))
    tk.Entry(root, textvariable=backend_var, width=42).grid(
        row=3, column=0, columnspan=2, padx=16, sticky="we"
    )

    tk.Label(root, text="Agent token").grid(row=4, column=0, **pad, sticky="w")
    tk.Button(
        root,
        text="Get my token",
        command=lambda: webbrowser.open(SETTINGS_PAGE_URL),
    ).grid(row=4, column=1, padx=16, sticky="e")
    token_var = tk.StringVar(value=(existing.token if existing else ""))
    tk.Entry(root, textvariable=token_var, width=42, show="*").grid(
        row=5, column=0, columnspan=2, padx=16, sticky="we"
    )

    tk.Label(root, text="Folder to watch on this computer").grid(row=6, column=0, **pad, sticky="w")
    folder_var = tk.StringVar(value=(existing.watch_folder if existing else ""))

    def browse() -> None:
        chosen = filedialog.askdirectory(title="Choose a folder for FileFlow to organize")
        if chosen:
            folder_var.set(chosen)

    tk.Entry(root, textvariable=folder_var, width=34).grid(
        row=7, column=0, padx=(16, 4), sticky="we"
    )
    tk.Button(root, text="Browse...", command=browse).grid(row=7, column=1, padx=(0, 16), sticky="e")

    def on_save() -> None:
        backend_url = backend_var.get().strip()
        token = token_var.get().strip()
        watch_folder = folder_var.get().strip()
        if not backend_url or not token or not watch_folder:
            messagebox.showerror("Missing information", "All three fields are required.")
            return
        save_config(backend_url, token, watch_folder)
        saved["backend_url"] = backend_url
        saved["token"] = token
        saved["watch_folder"] = watch_folder
        root.destroy()

    button_row = 8
    tk.Button(root, text="Save & Start", command=on_save, default="active").grid(
        row=button_row, column=1, padx=16, pady=16, sticky="e"
    )
    if existing is not None:
        tk.Button(root, text="Cancel", command=root.destroy).grid(
            row=button_row, column=0, padx=16, pady=16, sticky="w"
        )

    root.update_idletasks()
    width, height = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() - width) // 2
    y = (root.winfo_screenheight() - height) // 2
    root.geometry(f"+{x}+{y}")

    root.mainloop()

    if not saved:
        return None
    return AgentConfig(**saved)
