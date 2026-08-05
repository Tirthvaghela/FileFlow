import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")


class Settings:
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # The root under which each account's own watch folder defaults to a
    # subfolder (user_<id>) -- every account can point itself at a
    # different real folder later via Settings. Safe sandbox root by
    # default; point this at a real parent folder via .env once you're
    # ready to let FileFlow move real files.
    WATCH_FOLDER: Path = Path(
        os.getenv("WATCH_FOLDER", str(BACKEND_DIR / "sample_downloads"))
    ).resolve()

    RULES_CONFIG_PATH: Path = BACKEND_DIR / "config" / "rules.json"
    DB_PATH: Path = PROJECT_ROOT / "database" / "fileflow.db"
    LOG_FILE: Path = BACKEND_DIR / "logs" / "app.log"

    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "fileflow")

    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ]

    # Files still being written by the browser use these extensions.
    IGNORED_SUFFIXES: tuple[str, ...] = (".crdownload", ".part", ".tmp", ".download")

    # How long (seconds) to wait for a file's size to stop changing before
    # treating it as fully downloaded.
    STABILITY_POLL_INTERVAL: float = 1.0
    STABILITY_TIMEOUT: float = 30.0

    ARCHIVE_CHECK_INTERVAL_HOURS: int = 24

    # Optional real RPA integration: when enabled, the physical file-move
    # step is executed by UiPath Robot (uipath/FileFlowMove/MoveFile.xaml)
    # instead of a plain Python shutil.move. Off by default -- opt in via
    # .env once UiPath Robot is installed and the package has been
    # published (see uipath/FileFlowMove/). Never blocks organization if
    # disabled, missing, or failing: organizer.py always falls back to the
    # Python move.
    UIPATH_ENABLED: bool = os.getenv("UIPATH_ENABLED", "false").lower() == "true"
    UIPATH_ROBOT_EXE: Path | None = (
        Path(os.getenv("UIPATH_ROBOT_EXE")) if os.getenv("UIPATH_ROBOT_EXE") else None
    )
    UIPATH_PACKAGE_PATH: Path | None = (
        Path(os.getenv("UIPATH_PACKAGE_PATH")) if os.getenv("UIPATH_PACKAGE_PATH") else None
    )
    UIPATH_ENTRY_POINT: str = os.getenv("UIPATH_ENTRY_POINT", "MoveFile.xaml")
    UIPATH_TIMEOUT_SECONDS: int = int(os.getenv("UIPATH_TIMEOUT_SECONDS", "30"))

    # Weekly email digest via Resend (https://resend.com), sent to each
    # account's own registered email. Off by default -- sending only
    # happens once RESEND_API_KEY is set, and the scheduled job only runs
    # when WEEKLY_DIGEST_ENABLED is set.
    RESEND_API_KEY: str | None = os.getenv("RESEND_API_KEY") or None
    RESEND_FROM_EMAIL: str = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
    WEEKLY_DIGEST_ENABLED: bool = os.getenv("WEEKLY_DIGEST_ENABLED", "false").lower() == "true"

    # Signs session JWTs. Falls back to a fresh random key per process when
    # unset (fine for tests -- a run's tokens only ever need to validate
    # within that same run) but that means sessions won't survive a real
    # server restart. Set SECRET_KEY in .env for persistent sessions.
    SECRET_KEY: str = os.getenv("SECRET_KEY") or secrets.token_hex(32)

    # Brute-force / spam protection on /api/auth/login and /register,
    # per caller IP. Login gets a short, tight window (repeated password
    # guesses); registration gets a longer one (account-creation spam).
    LOGIN_RATE_LIMIT_MAX: int = int(os.getenv("LOGIN_RATE_LIMIT_MAX", "5"))
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: float = float(
        os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300")
    )
    REGISTER_RATE_LIMIT_MAX: int = int(os.getenv("REGISTER_RATE_LIMIT_MAX", "5"))
    REGISTER_RATE_LIMIT_WINDOW_SECONDS: float = float(
        os.getenv("REGISTER_RATE_LIMIT_WINDOW_SECONDS", "3600")
    )


settings = Settings()

settings.WATCH_FOLDER.mkdir(parents=True, exist_ok=True)
settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def resolve_watch_folder(path) -> Path:
    """Validate and create a folder to be watched. Raises OSError if it
    can't be created (bad path, no permission, etc)."""
    resolved = Path(path).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def default_watch_folder_for(user_id: int) -> Path:
    """Each account's default watched folder -- a private subfolder under
    the shared watch root, created the first time it's needed. Editable
    per-account afterward via Settings."""
    return resolve_watch_folder(settings.WATCH_FOLDER / f"user_{user_id}")
