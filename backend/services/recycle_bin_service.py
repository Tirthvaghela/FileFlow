import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rules.rule_engine import get_rule_engine

logger = logging.getLogger("fileflow.recyclebin")

# winshell/pywin32 are Windows-only (this whole app targets Windows -- see
# the remote agent installer, UiPath Robot integration) and wrap Shell COM
# APIs that have no cross-platform equivalent. Imported lazily/guarded so a
# non-Windows dev environment can still import this module (and the
# scheduler that wires it in) without crashing at startup; every function
# below just no-ops instead.
try:
    import winshell

    _WINSHELL_AVAILABLE = sys.platform == "win32"
except ImportError:
    winshell = None
    _WINSHELL_AVAILABLE = False


def _find_recycle_bin_item(original_path: str, expected_size: int):
    """Best-effort lookup of a specific file inside the Recycle Bin by the
    path it was sent from. winshell's RecycleBinItem.original_filename()
    sometimes drops the file's extension and sometimes doesn't -- confirmed
    empirically to depend on the extension itself (Windows Explorer's own
    "hide extensions for known file types" setting affects which shell API
    winshell ends up reading, and that only applies to extensions with a
    registered file type), so neither the full path nor the extension-less
    stem alone is a safe assumption -- this accepts either. Cross-checked
    against the file's size at deletion time so a different file that
    happens to share a name/stem (e.g. "report.txt" vs "report.pdf") can't
    produce a false match. Returns None if it isn't there -- already
    restored by the user via Explorer, already evicted by Windows' own
    Recycle Bin size cap, or (rarely) enumeration itself failing -- any of
    which just means there's nothing left for this sweep to do."""
    stem = str(Path(original_path).with_suffix(""))
    try:
        for item in winshell.recycle_bin():
            try:
                orig = str(item.original_filename())
                if orig != original_path and orig != stem:
                    continue
                if item.getsize() != expected_size:
                    continue
                return item
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not enumerate the Recycle Bin: %s", exc)
        return None
    return None


def _permanently_delete_item(item) -> bool:
    """Removes exactly one Recycle Bin entry's on-disk halves: the visible
    "$R..." data file and its paired "$I..." metadata file (same base name,
    "$I" prefix instead of "$R") -- Windows keeps both per deleted item, and
    only removing the first leaves an orphaned metadata stub behind.
    Never touches anything else in $Recycle.Bin, and never calls the OS
    "empty recycle bin" operation, which would take every other file in it
    too."""
    real_path = Path(item.real_filename())
    ok = True
    try:
        real_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not permanently delete %s: %s", real_path, exc)
        ok = False

    if real_path.name.startswith("$R"):
        metadata_path = real_path.with_name("$I" + real_path.name[2:])
        try:
            metadata_path.unlink(missing_ok=True)
        except OSError:
            pass  # cosmetic leftover at worst; the visible file is already gone

    return ok


def purge_expired_deleted_files(db, user: dict) -> int:
    """Permanently empties out only the Recycle Bin entries FileFlow itself
    put there (via delete_category_file), once each has sat past this
    account's configured retention window. Every "deleted" activity_log row
    was necessarily created by a delete performed on this same machine --
    delete_category_file refuses outright for agent-connected accounts
    rather than queuing it (see routes.py), so there's no case where this
    sweep needs to reach a different machine's Recycle Bin.

    Returns the number of entries actually purged."""
    if not _WINSHELL_AVAILABLE:
        return 0

    watch_root = Path(user["watch_folder"])
    engine = get_rule_engine(db, user["id"], watch_root)
    retention_days = engine.rules.get("recycle_bin_retention_days", 30)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    rows = list(
        db.activity_log.find(
            {
                "user_id": user["id"],
                "action": "deleted",
                "recycle_bin_purged": {"$ne": True},
                "timestamp": {"$lte": cutoff},
            }
        )
    )

    purged = 0
    for row in rows:
        item = _find_recycle_bin_item(row["source_path"], row.get("file_size", 0))
        if item is not None:
            if _permanently_delete_item(item):
                purged += 1
        # Whether found-and-purged or already gone by some other means,
        # this row is done -- mark it either way so the sweep doesn't
        # re-enumerate the same stale row forever.
        db.activity_log.update_one({"_id": row["_id"]}, {"$set": {"recycle_bin_purged": True}})

    return purged


def purge_all_users_recycle_bins(db) -> int:
    """Scheduled sweep entry point: runs purge_expired_deleted_files() for
    every account, isolating one account's failure from the rest exactly
    like the existing archive/organize sweeps do."""
    if not _WINSHELL_AVAILABLE:
        return 0

    total = 0
    for user in list(db.users.find()):
        try:
            total += purge_expired_deleted_files(db, user)
        except Exception:
            logger.exception("Recycle Bin purge failed for user %d -- skipping.", user["id"])

    if total:
        logger.info("Permanently purged %d Recycle Bin entr%s", total, "y" if total == 1 else "ies")
    return total
