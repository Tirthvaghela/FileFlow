import logging
import time
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from automation.file_ops import move_lock as _move_lock
from automation.organizer import organize_existing_files
from config.settings import all_watch_folders, settings
from database.db import db, insert_with_id
from models.models import new_activity_log
from rules.rule_engine import get_rule_engine, is_within_watch_folder
from services.agent_service import enqueue_agent_command, is_agent_connected
from services.digest_service import send_weekly_digest
from services.recycle_bin_service import purge_all_users_recycle_bins
from services.storage_threshold_service import check_all_storage_thresholds

logger = logging.getLogger("fileflow.archive")


def _archive_old_files_for_user(user: dict) -> int:
    """Sweeps every folder this account watches (primary plus any
    additional ones) -- each gets its own Archive subfolder inside itself,
    all governed by the same shared rules (archive_after_days,
    archive_folder name)."""
    total = 0
    for watch_root in all_watch_folders(user):
        if watch_root.exists():
            total += _archive_old_files_in_folder(user, watch_root)
    return total


def _archive_old_files_in_folder(user: dict, watch_root: Path) -> int:
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

        # Same _move_lock automation/organizer.py's process_file/undo/
        # reclassify already hold around their own "resolve a unique
        # destination name, then rename into it" sequence -- this scheduled
        # sweep was the one file-moving path left that didn't, so it could
        # race one of those (or the storage-threshold auto-archive below)
        # renaming a different file to this exact same destination path,
        # the same non-atomic-on-Windows collision move_lock itself
        # documents (two renames can both pass the exists() check for the
        # same target before either has actually moved anything).
        with _move_lock:
            dest = archive_root / path.name
            counter = 1
            while dest.exists():
                dest = archive_root / f"{path.stem} ({counter}){path.suffix}"
                counter += 1

            original_category = path.parent.name
            try:
                file_size = path.stat().st_size
                # .rename(), not shutil.move(): shutil's own fallback silently
                # absorbs a "destination already exists" collision by copying
                # over it instead of raising (see the equivalent fix in
                # automation/organizer.py) -- a real risk here since this scan
                # can race a manual reclassify/undo touching the same file
                # while the scheduled sweep is mid-run.
                path.rename(dest)
            except OSError:
                logger.warning(
                    "Could not archive %s for user %d -- left in place, will retry next sweep.",
                    path, user["id"],
                )
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
        try:
            total += _archive_old_files_for_user(user)
        except Exception:
            # One account's bad environment (an unreadable/locked folder,
            # a permission issue) must not silently skip every account
            # that happens to sort after it in this sweep.
            logger.exception("Archive sweep failed for user %d -- skipping.", user["id"])

    if total:
        logger.info("Archived %d file(s)", total)
    return total


def _weekly_digest_job() -> None:
    for user in list(db.users.find()):
        try:
            send_weekly_digest(db, user)
        except Exception:
            logger.exception("Weekly digest failed for user %d -- skipping.", user["id"])


def _run_scheduled_organize_for_user(user: dict, today: str) -> None:
    watch_root = Path(user["watch_folder"])
    engine = get_rule_engine(db, user["id"], watch_root)
    if not engine.rules.get("scheduled_organize_enabled", False):
        return

    target_time = engine.rules.get("scheduled_organize_time", "02:00")
    # Wall-clock local time, deliberately not UTC: a user who types "02:00"
    # means their own machine's 2am, and this app's actual deployment model
    # (see the remote-agent feature) is the backend and the account it
    # serves running on the same machine -- there's no separate per-account
    # timezone setting to convert from, so local time is both the simplest
    # option and the one that matches what the user actually typed.
    now = datetime.now()
    if now.strftime("%H:%M") < target_time:
        return
    if user.get("scheduled_organize_last_run") == today:
        # Already ran today -- the check interval is far shorter than a
        # day, so without this a single "past 2am" state would re-trigger
        # on every subsequent check until midnight.
        return

    if is_agent_connected(user):
        # Only queues the command here -- the agent, not this process, does
        # the actual scan/move, and reports its own outcome asynchronously
        # via POST /api/agent/commands/{id}/complete once it next polls.
        enqueue_agent_command(db, user["id"], "organize_existing", {})
        logger.info("Scheduled organize for user %d: dispatched to agent.", user["id"])
    else:
        # Unlike enqueue_agent_command above, this runs synchronously and
        # its result was previously discarded here -- logging it (matching
        # archive_old_files()'s own "log the counts" convention in this
        # same file) is what actually distinguishes "ran and organized N
        # files" from "ran and found nothing to do" in the log a scheduled
        # job's "executed successfully" message alone cannot.
        result = organize_existing_files(db, user)
        logger.info(
            "Scheduled organize for user %d: scanned %d, organized %d, %d duplicate(s), %d error(s).",
            user["id"], result["scanned"], result["organized"], result["duplicates"], result["errors"],
        )
    db.users.update_one({"_id": user["id"]}, {"$set": {"scheduled_organize_last_run": today}})


def run_scheduled_organizes() -> None:
    """Runs each account's own "organize existing files" sweep once it
    passes their configured daily time -- an unattended equivalent of
    clicking "Organize existing files now" on a schedule, rather than only
    on real-time drops or a manual click."""
    today = datetime.now().date().isoformat()
    for user in list(db.users.find()):
        try:
            _run_scheduled_organize_for_user(user, today)
        except Exception:
            logger.exception("Scheduled organize failed for user %d -- skipping.", user["id"])


def run_recycle_bin_purge() -> int:
    return purge_all_users_recycle_bins(db)


def run_storage_threshold_check() -> None:
    check_all_storage_thresholds(db)


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    # next_run_time is deliberately left at its default (unspecified) on
    # every job below, NOT passed as None -- APScheduler's add_job() treats
    # next_run_time=None as "add this job paused" (see its docstring), which
    # silently disabled every one of these jobs forever, including the
    # nightly organize sweep: they were registered but never actually fired,
    # on any schedule. Leaving it unspecified lets IntervalTrigger compute
    # the normal first fire time of "now + interval" -- still not immediate
    # on every server restart, just no longer permanently off.
    scheduler.add_job(
        archive_old_files,
        "interval",
        hours=settings.ARCHIVE_CHECK_INTERVAL_HOURS,
        id="archive_old_files",
    )
    scheduler.add_job(
        run_recycle_bin_purge,
        "interval",
        hours=settings.ARCHIVE_CHECK_INTERVAL_HOURS,
        id="recycle_bin_purge",
    )
    scheduler.add_job(
        run_storage_threshold_check,
        "interval",
        hours=settings.ARCHIVE_CHECK_INTERVAL_HOURS,
        id="storage_threshold_check",
    )
    if settings.WEEKLY_DIGEST_ENABLED:
        scheduler.add_job(
            _weekly_digest_job,
            "interval",
            weeks=1,
            id="weekly_digest",
        )
    scheduler.add_job(
        run_scheduled_organizes,
        "interval",
        minutes=settings.SCHEDULED_ORGANIZE_CHECK_INTERVAL_MINUTES,
        id="scheduled_organizes",
    )
    scheduler.start()
    return scheduler
