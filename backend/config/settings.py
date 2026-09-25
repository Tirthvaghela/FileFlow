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

    # How often the scheduler checks whether any account's configured
    # scheduled-organize time has arrived. Minutes, not hours, since a
    # per-account clock time (e.g. "02:00") needs a check granularity fine
    # enough to actually catch that moment, unlike the once-a-day archive
    # sweep above.
    SCHEDULED_ORGANIZE_CHECK_INTERVAL_MINUTES: int = 5

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

    # Outgoing email (weekly digest, password reset) via SMTP -- e.g. Gmail
    # with an App Password (myaccount.google.com/apppasswords, requires
    # 2-Step Verification). Sending only happens once both SMTP_USERNAME
    # and SMTP_PASSWORD are set; the scheduled digest job additionally only
    # runs when WEEKLY_DIGEST_ENABLED is set.
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str | None = os.getenv("SMTP_USERNAME") or None
    SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD") or None
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL") or os.getenv("SMTP_USERNAME") or ""
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
    PASSWORD_RESET_RATE_LIMIT_MAX: int = int(os.getenv("PASSWORD_RESET_RATE_LIMIT_MAX", "5"))
    PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS: float = float(
        os.getenv("PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS", "3600")
    )
    # Same reasoning as LOGIN_RATE_LIMIT_* above, for the second half of a
    # 2FA-enabled login: a valid pending_token (5-minute lifetime) proves
    # only that the password was correct, not who's holding it, so nothing
    # else bounds how many TOTP/backup-code guesses can be made against it
    # -- the login limiter only throttles minting a *new* pending token,
    # not verify attempts against one already obtained.
    TWOFA_VERIFY_RATE_LIMIT_MAX: int = int(os.getenv("TWOFA_VERIFY_RATE_LIMIT_MAX", "5"))
    TWOFA_VERIFY_RATE_LIMIT_WINDOW_SECONDS: float = float(
        os.getenv("TWOFA_VERIFY_RATE_LIMIT_WINDOW_SECONDS", "300")
    )

    # Base URL of the deployed frontend -- used to build the link inside the
    # password reset email. Defaults to the local Vite dev server.
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

    # How long a "forgot password" link stays valid before it must be
    # re-requested.
    PASSWORD_RESET_TOKEN_EXPIRY_MINUTES: int = int(
        os.getenv("PASSWORD_RESET_TOKEN_EXPIRY_MINUTES", "30")
    )

    # AI Rule Generator (services/ai_provider.py, services/ai_rule_service.py):
    # turns a natural-language request into a structured rule PROPOSAL only --
    # never saves a rule or touches a file itself. AI_PROVIDER selects which
    # of the two request/response shapes services/ai_provider.py builds --
    # "anthropic" (default) or "gemini"; adding a third provider means adding
    # another entry to that module's _PROVIDERS dict, not branching further
    # here. Whichever provider's own API key env var is unset simply makes
    # every request fail with a clean "AI service is not configured"
    # response rather than raising.
    AI_PROVIDER: str = (os.getenv("AI_PROVIDER") or "anthropic").strip().lower()
    ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY") or None
    # Resolved once here so services/ai_provider.py never has to know which
    # env var backs whichever provider is actually selected.
    AI_PROVIDER_API_KEY: str | None = GEMINI_API_KEY if AI_PROVIDER == "gemini" else ANTHROPIC_API_KEY
    AI_PROVIDER_MODEL: str = os.getenv(
        "AI_PROVIDER_MODEL",
        "gemini-3.6-flash" if AI_PROVIDER == "gemini" else "claude-haiku-4-5-20251001",
    )
    AI_PROVIDER_BASE_URL: str = os.getenv(
        "AI_PROVIDER_BASE_URL", "https://api.anthropic.com/v1/messages"
    )
    GEMINI_API_BASE_URL: str = os.getenv(
        "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/models"
    )
    AI_PROVIDER_TIMEOUT_SECONDS: float = float(os.getenv("AI_PROVIDER_TIMEOUT_SECONDS", "20"))

    # Abuse protection on /api/rules/ai-generate, per caller IP -- same
    # fixed-window mechanism and per-IP keying as every other limiter here
    # (see api/rate_limit.py), since each AI call has a real provider cost.
    AI_RULE_GENERATE_RATE_LIMIT_MAX: int = int(os.getenv("AI_RULE_GENERATE_RATE_LIMIT_MAX", "20"))
    AI_RULE_GENERATE_RATE_LIMIT_WINDOW_SECONDS: float = float(
        os.getenv("AI_RULE_GENERATE_RATE_LIMIT_WINDOW_SECONDS", "3600")
    )

    # AI Unclassified File Suggestions (services/ai_unclassified_service.py):
    # at most this many distinct file-name groups go into a single AI
    # request -- a hard, configurable ceiling rather than an unbounded
    # prompt, matching FileFlow's existing small/bounded batch sizes
    # (Organization Preview never paginates either, for the same reason).
    AI_UNCLASSIFIED_MAX_BATCH_SIZE: int = int(os.getenv("AI_UNCLASSIFIED_MAX_BATCH_SIZE", "15"))
    AI_UNCLASSIFIED_RATE_LIMIT_MAX: int = int(os.getenv("AI_UNCLASSIFIED_RATE_LIMIT_MAX", "20"))
    AI_UNCLASSIFIED_RATE_LIMIT_WINDOW_SECONDS: float = float(
        os.getenv("AI_UNCLASSIFIED_RATE_LIMIT_WINDOW_SECONDS", "3600")
    )

    # Smart Duplicate Groups (automation/file_ops.py::build_duplicate_groups_result,
    # services/duplicate_service.py): a purely deterministic SHA-256 content
    # scan, no AI/rate limiting involved -- this cap only bounds how many
    # duplicate-group *details* one response returns (summary counts always
    # reflect the full scan regardless); `truncated` discloses when it was hit.
    DUPLICATE_ANALYSIS_MAX_GROUPS_RETURNED: int = int(
        os.getenv("DUPLICATE_ANALYSIS_MAX_GROUPS_RETURNED", "50")
    )

    # Natural Language File Search (services/file_search_service.py,
    # automation/file_ops.py::search_files_by_query): a hard ceiling on how
    # many results a single search response returns -- SearchQuery.limit
    # (models/schemas.py) is separately capped at 100 per-request, but this
    # is the server-side backstop regardless of what a client asks for.
    FILE_SEARCH_MAX_RESULT_LIMIT: int = int(os.getenv("FILE_SEARCH_MAX_RESULT_LIMIT", "100"))
    # Same per-IP fixed-window abuse protection as every other AI-backed
    # endpoint (api/rate_limit.py) -- each search's AI interpretation step
    # has a real provider cost.
    AI_FILE_SEARCH_RATE_LIMIT_MAX: int = int(os.getenv("AI_FILE_SEARCH_RATE_LIMIT_MAX", "20"))
    AI_FILE_SEARCH_RATE_LIMIT_WINDOW_SECONDS: float = float(
        os.getenv("AI_FILE_SEARCH_RATE_LIMIT_WINDOW_SECONDS", "3600")
    )


settings = Settings()

settings.WATCH_FOLDER.mkdir(parents=True, exist_ok=True)
settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def resolve_watch_folder(path) -> Path:
    """Validate and create a folder to be watched. Raises OSError if it
    can't be created (bad path, no permission, etc).

    Deliberately has no containment check against WATCH_FOLDER or any
    other root -- an account may point its own watch folder at any real
    path this process can reach; the only boundary enforced anywhere
    (_check_folder_available, api/routes.py) is *cross-account* overlap.
    This is the intended, tested contract (backend/tests/test_multi_user_
    isolation.py) for FileFlow's actual deployment model: one self-hosted
    instance shared by a trusted group, where "per-account isolation"
    means accounts can't reach each other's data/files -- not that the
    backend host's own filesystem is defended from its own registered
    users. See README's "Known issues" for the deployment assumption this
    relies on before adding open/untrusted self-service registration."""
    resolved = Path(path).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def paths_overlap(a: Path, b: Path) -> bool:
    """True if `a` and `b` are the same folder, or either is nested inside
    the other. An exact-match check alone isn't enough to keep two
    accounts' watch folders isolated -- pointing your own watch folder at a
    *subfolder* of someone else's tree (or vice versa) gives you the same
    access to their files without ever matching their path exactly."""
    return a == b or a in b.parents or b in a.parents


def default_watch_folder_for(user_id: int) -> Path:
    """Each account's default watched folder -- a private subfolder under
    the shared watch root, created the first time it's needed. Editable
    per-account afterward via Settings."""
    return resolve_watch_folder(settings.WATCH_FOLDER / f"user_{user_id}")


def all_watch_folders(user: dict) -> list[Path]:
    """Every folder this account has FileFlow watching -- the primary
    watch_folder plus any additional_watch_folders, all sharing the same
    rules. The single choke point for "every folder", so archiving, the
    scheduled sweep, and organize-existing all agree on what "this
    account's folders" means instead of each hardcoding watch_folder alone
    and silently ignoring additional ones."""
    folders = [Path(user["watch_folder"])]
    folders.extend(Path(f) for f in user.get("additional_watch_folders", None) or [])
    return folders


def watch_folder_containing(user: dict, path: Path) -> Path:
    """Which of this account's watch folders `path` currently lives
    inside -- computing a destination for an already-organized file (e.g.
    reclassify) must resolve it relative to the SAME watch folder the file
    actually came from, not unconditionally the primary one, or it would
    relocate the file into a completely different top-level tree (a
    same-drive rename wouldn't even raise -- it would just silently move
    the file into the wrong folder; a different-drive additional folder
    would raise OSError instead). Falls back to the primary watch_folder
    if `path` isn't inside any of this account's known folders."""
    try:
        resolved = path.resolve()
    except OSError:
        return Path(user["watch_folder"])
    for root in all_watch_folders(user):
        try:
            root_resolved = root.resolve()
        except OSError:
            continue
        if resolved == root_resolved or root_resolved in resolved.parents:
            return root
    return Path(user["watch_folder"])
