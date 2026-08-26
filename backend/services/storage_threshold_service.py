import logging
from pathlib import Path

from automation.file_ops import move_lock as _move_lock
from automation.organizer import list_category_files
from config.settings import all_watch_folders
from database.db import insert_with_id
from models.models import new_activity_log
from rules.classifier import is_within_watch_folder
from rules.rule_engine import get_rule_engine
from services.notification_service import notify

logger = logging.getLogger("fileflow.storage_threshold")

_GB = 1024 ** 3


def _format_gb(num_bytes: int) -> str:
    return f"{num_bytes / _GB:.1f} GB"


def _distinct_category_names(user: dict) -> set[str]:
    names: set[str] = set()
    for root in all_watch_folders(user):
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if entry.is_dir():
                names.add(entry.name)
    return names


def _archive_oldest_until_under_threshold(
    db, user: dict, engine, files: list[dict], threshold_bytes: int, total_bytes: int
) -> int:
    """Moves the oldest files in a single over-threshold category into their
    own watch root's Archive folder (same destination/collision rules as the
    age-based archive sweep) until the category's remaining size drops back
    at or under the threshold, or there's nothing left to move. Returns how
    many files were archived."""
    archive_folder_name = engine.archive_folder
    remaining = total_bytes
    archived_count = 0

    for file in sorted(files, key=lambda f: f["modified_at"]):
        if remaining <= threshold_bytes:
            break

        path = Path(file["path"])
        watch_root = path.parent.parent
        if not is_within_watch_folder(archive_folder_name, watch_root):
            logger.warning(
                "Configured archive folder %r resolves outside the watch "
                "folder -- skipping auto-archive for user %d.",
                archive_folder_name, user["id"],
            )
            break
        archive_root = watch_root / archive_folder_name
        archive_root.mkdir(parents=True, exist_ok=True)

        # Same _move_lock as the age-based archive sweep (scheduler/
        # archive_scheduler.py) -- this auto-archive can run in the same
        # scheduled pass and both resolve/rename into the same Archive
        # folder, so the destination-collision race that lock exists for
        # applies here identically.
        with _move_lock:
            dest = archive_root / path.name
            counter = 1
            while dest.exists():
                dest = archive_root / f"{path.stem} ({counter}){path.suffix}"
                counter += 1

            try:
                path.rename(dest)
            except OSError:
                logger.warning("Storage-threshold auto-archive: %s vanished before it could move.", path)
                continue

        insert_with_id(
            db,
            "activity_log",
            new_activity_log(
                user_id=user["id"],
                original_filename=path.name,
                final_filename=dest.name,
                source_path=str(path),
                destination_path=str(dest),
                category=path.parent.name,
                action="archived",
                file_size=file["size_bytes"],
            ),
        )
        remaining -= file["size_bytes"]
        archived_count += 1

    return archived_count


def _check_storage_thresholds_for_user(db, user: dict) -> None:
    watch_root = Path(user["watch_folder"])
    engine = get_rule_engine(db, user["id"], watch_root)
    threshold_gb = engine.rules.get("storage_alert_threshold_gb", 0)
    if not threshold_gb:
        return
    threshold_bytes = int(threshold_gb * _GB)
    archive_folder_name = engine.archive_folder

    for category in _distinct_category_names(user):
        if category == archive_folder_name:
            # Archiving *into* the same folder that's already over the
            # threshold wouldn't reduce anything -- and for an Archive
            # folder that's genuinely just accumulating, that's expected
            # growth, not something to auto-archive out of itself.
            continue

        files = list_category_files(user, category)
        total_bytes = sum(f["size_bytes"] for f in files)
        if total_bytes <= threshold_bytes:
            continue

        archived_count = _archive_oldest_until_under_threshold(
            db, user, engine, files, threshold_bytes, total_bytes
        )
        if archived_count:
            message = (
                f"'{category}' was using {_format_gb(total_bytes)} "
                f"(threshold {_format_gb(threshold_bytes)}) -- automatically "
                f"archived the {archived_count} oldest file(s) to bring it back down."
            )
        else:
            message = (
                f"'{category}' is using {_format_gb(total_bytes)}, over your "
                f"{_format_gb(threshold_bytes)} alert threshold."
            )
        notify("Storage threshold exceeded", message, engine.rules)


def check_all_storage_thresholds(db) -> None:
    """Scheduled sweep entry point: checks every account's categories
    against its own configured storage_alert_threshold_gb, isolating one
    account's failure from the rest like the other scheduled sweeps."""
    for user in list(db.users.find()):
        try:
            _check_storage_thresholds_for_user(db, user)
        except Exception:
            logger.exception("Storage threshold check failed for user %d -- skipping.", user["id"])
