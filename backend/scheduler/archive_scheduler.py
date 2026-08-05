import logging
import shutil
import time
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from config.settings import settings
from database.db import db, insert_with_id
from models.models import new_activity_log
from rules.rule_engine import get_rule_engine, is_within_watch_folder
from services.digest_service import send_weekly_digest

logger = logging.getLogger("fileflow.archive")


def _archive_old_files_for_user(user: dict) -> int:
    watch_root = Path(user["watch_folder"])
    engine = get_rule_engine(db, user["id"], watch_root)

    archive_folder_name = engine.archive_folder
    if not is_within_watch_folder(archive_folder_name, watch_root):
        # A typo'd or malicious archive_folder (e.g. "..\\..\\Documents")
        # must never send this unattended, scheduled job moving files
        # outside the tree that account's FileFlow instance was told to
        # manage.
        logger.warning(
            "Configured archive folder %r resolves outside the watch "
            "folder -- falling back to 'Archive' instead.",
            archive_folder_name,
        )
        archive_folder_name = "Archive"
    archive_root = watch_root / archive_folder_name
    archive_root.mkdir(parents=True, exist_ok=True)

    cutoff = time.time() - engine.archive_after_days * 86400
    archived_count = 0
    for path in watch_root.rglob("*"):
        if not path.is_file():
            continue
        if archive_root in path.parents:
            continue
        try:
            if path.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue

        dest = archive_root / path.name
        counter = 1
        while dest.exists():
            dest = archive_root / f"{path.stem} ({counter}){path.suffix}"
            counter += 1

        original_category = path.parent.name
        file_size = path.stat().st_size
        shutil.move(str(path), str(dest))

        insert_with_id(
            db,
            "activity_log",
            new_activity_log(
                user_id=user["id"],
                original_filename=path.name,
                final_filename=dest.name,
                source_path=str(path),
                destination_path=str(dest),
                category=original_category,
                action="archived",
                file_size=file_size,
            ),
        )
        archived_count += 1

    return archived_count


def archive_old_files() -> int:
    """Move files older than each account's own `archive_after_days` into
    their own Archive folder. Returns the total number of files archived
    across every registered account."""
    total = 0
    for user in list(db.users.find()):
        total += _archive_old_files_for_user(user)

    if total:
        logger.info("Archived %d file(s)", total)
    return total


def _weekly_digest_job() -> None:
    for user in list(db.users.find()):
        send_weekly_digest(db, user)


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        archive_old_files,
        "interval",
        hours=settings.ARCHIVE_CHECK_INTERVAL_HOURS,
        id="archive_old_files",
        next_run_time=None,
    )
    if settings.WEEKLY_DIGEST_ENABLED:
        scheduler.add_job(
            _weekly_digest_job,
            "interval",
            weeks=1,
            id="weekly_digest",
            next_run_time=None,
        )
    scheduler.start()
    return scheduler
