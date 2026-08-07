# PyInstaller spec for the FileFlow Agent -- build with:
#   pyinstaller agent/fileflow_agent.spec
# from the repo root, using a venv that already has agent/requirements.txt
# installed (plus `pip install pyinstaller`).
#
# One-folder build (COLLECT, not a single .exe): faster startup and much
# easier to troubleshoot than --onefile, and the Inno Setup installer
# still hands the end user a single download either way.

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

REPO_ROOT = Path(SPECPATH).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"

# agent/watcher.py, agent/commands.py etc. import automation.file_ops,
# rules.classifier, config.settings, services.notification_service, and
# services.uipath_service from backend/ -- the same sys.path trick
# agent/main.py does at runtime, mirrored here so PyInstaller's static
# analysis can resolve them too.
pathex = [str(REPO_ROOT), str(BACKEND_DIR)]

# plyer picks its notification backend dynamically at import time based on
# the OS, which static analysis can miss -- collect every plyer submodule
# explicitly rather than trying to guess the one Windows needs.
hiddenimports = collect_submodules("plyer")

a = Analysis(
    [str(REPO_ROOT / "agent" / "main.py")],
    pathex=pathex,
    binaries=[],
    datas=[
        (str(REPO_ROOT / "agent" / "assets" / "icon.ico"), "agent/assets"),
        (str(REPO_ROOT / "agent" / "VERSION"), "agent"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FileFlowAgent",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(REPO_ROOT / "agent" / "assets" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="FileFlowAgent",
)
