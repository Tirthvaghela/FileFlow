import asyncio
import logging
import threading
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from automation.organizer import process_file
from database.db import db as default_db
from models.schemas import ActivityLogOut
from rules.rule_engine import get_rule_engine
from services.agent_service import is_agent_connected

logger = logging.getLogger("fileflow.watcher")


def _is_inside_managed_subfolder(path: Path, watch_root: Path) -> bool:
    try:
        relative = path.relative_to(watch_root)
    except ValueError:
        return False
    return len(relative.parts) > 1


class DownloadHandler(FileSystemEventHandler):
    """Watches one user's folder. One instance per registered user, all
    scheduled on the same shared Observer."""

    def __init__(self, loop: asyncio.AbstractEventLoop, broadcast, db, user_id: int, watch_root: Path):
        super().__init__()
        self.loop = loop
        self.broadcast = broadcast
        self.db = db
        self.user_id = user_id
        self.watch_root = watch_root

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle(Path(event.src_path))

    def on_moved(self, event):
        if event.is_directory:
            return
        self._handle(Path(event.dest_path))

    def _handle(self, path: Path):
        # If a remote agent is actively checked in for this account, it's
        # already watching this exact folder on the machine that actually
        # owns it -- reacting here too means the same file gets raced by
        # two independent watchers (this backend's local Observer, which
        # runs regardless of where the folder physically lives, and the
        # agent), one moving/logging it and the other a beat behind seeing
        # it as an unexplained duplicate. Every other local-filesystem
        # action (undo, reclassify, organize-existing) already defers to
        # the agent the same way -- see services.agent_service.
        user = self.db.users.find_one({"_id": self.user_id})
        if user and is_agent_connected(user):
            return
        engine = get_rule_engine(self.db, self.user_id, self.watch_root)
        if not engine.rules.get("realtime_monitoring_enabled", True):
            return
        if _is_inside_managed_subfolder(path, self.watch_root):
            return
        threading.Thread(target=self._process_in_thread, args=(path,), daemon=True).start()

    def _process_in_thread(self, path: Path):
        try:
            user = {"id": self.user_id, "watch_folder": str(self.watch_root)}
            log = process_file(path, self.db, user)
            if log is not None:
                payload = ActivityLogOut.model_validate(log).model_dump(mode="json")
                asyncio.run_coroutine_threadsafe(
                    self.broadcast(payload, self.user_id), self.loop
                )
        except Exception:
            logger.exception("Failed to process %s", path)


_observer: Observer | None = None
_loop: asyncio.AbstractEventLoop | None = None
_broadcast = None
_db = None
# user_id -> {folder path string: watchdog ObservedWatch}. A folder string
# (not a role like "primary") is the key because that's the one thing
# guaranteed unique per entry -- a user can have several additional
# folders scheduled at once, all siblings, only one of which (tracked
# separately in _primary_folder below) is "the" watch_folder on their
# account record.
_watches: dict[int, dict[str, object]] = {}
# user_id -> that user's current primary watch_folder, as a path string.
# Only update_watch_folder() (repointing the primary) needs to know which
# one entry in _watches[user_id] is the primary rather than an additional
# folder -- additional folders are added/removed by their own path and
# never implicitly replaced.
_primary_folder: dict[int, str] = {}
# FastAPI runs each sync request in its own thread, so two requests for the
# same user (a double-submitted Settings save, or a slow request plus an
# impatient retry) can call into this module concurrently. Reentrant so
# update_watch_folder() can hold it across its own call into _schedule().
_lock = threading.RLock()


def _schedule(user_id: int, watch_root: Path) -> None:
    # The folder can go missing between registration and now (moved,
    # deleted, external cleanup) -- recreate it rather than letting
    # observer.schedule() raise and take the whole server down with it.
    try:
        watch_root.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.exception(
            "Could not create/access watch folder %s for user %d -- skipping.",
            watch_root, user_id,
        )
        return

    handler = DownloadHandler(_loop, _broadcast, _db, user_id, watch_root)
    with _lock:
        watch = _observer.schedule(handler, str(watch_root), recursive=True)
        _watches.setdefault(user_id, {})[str(watch_root)] = watch


def _unschedule_one(user_id: int, path_str: str) -> None:
    with _lock:
        # pop (not get): claims this watch for removal so a concurrent call
        # for the same path can't also try to unschedule it -- watchdog's
        # unschedule() raises if called twice on the same watch.
        user_watches = _watches.get(user_id)
        watch = user_watches.pop(path_str, None) if user_watches else None
        if watch is not None:
            try:
                _observer.unschedule(watch)
            except KeyError:
                # Already removed by a racing call for this same path --
                # safe to ignore, the end state is the same either way.
                pass


def start_watcher(loop: asyncio.AbstractEventLoop, broadcast, db=None) -> Observer:
    """Start watching every already-registered user's folder(s) -- their
    primary watch_folder plus any additional_watch_folders. New accounts
    and new folders get added live afterward via add_user_watch() /
    add_additional_watch(), no restart needed."""
    global _observer, _loop, _broadcast, _db
    _loop = loop
    _broadcast = broadcast
    _db = db if db is not None else default_db

    observer = Observer()
    _observer = observer
    total = 0
    for user in _db.users.find():
        watch_folder = user.get("watch_folder")
        if not watch_folder:
            logger.warning(
                "Skipping user %r -- no watch_folder on record.", user.get("email")
            )
            continue
        _schedule(user["id"], Path(watch_folder))
        _primary_folder[user["id"]] = str(Path(watch_folder))
        total += 1
        for extra in user.get("additional_watch_folders", None) or []:
            _schedule(user["id"], Path(extra))
            total += 1
    observer.start()
    logger.info("Watching %d folder(s)", total)
    return observer


def add_user_watch(user_id: int, watch_root: Path) -> None:
    """Start watching a newly-registered user's primary folder on the
    already-running observer."""
    if _observer is None:
        return
    _schedule(user_id, watch_root)
    _primary_folder[user_id] = str(watch_root)
    logger.info("Watching %s for user %d", watch_root, user_id)


def add_additional_watch(user_id: int, watch_root: Path) -> None:
    """Start watching an extra folder for an account that already has a
    primary one -- both are watched independently and organized with the
    same rules, side by side."""
    if _observer is None:
        return
    _schedule(user_id, watch_root)
    logger.info("Watching additional folder %s for user %d", watch_root, user_id)


def remove_additional_watch(user_id: int, watch_root: Path) -> None:
    """Stop watching one specific additional folder, leaving the primary
    folder (and any other additional ones) untouched."""
    if _observer is None:
        return
    _unschedule_one(user_id, str(watch_root))
    logger.info("Stopped watching additional folder %s for user %d", watch_root, user_id)


def remove_user_watch(user_id: int) -> None:
    """Stop watching every folder an account has -- primary and additional
    alike -- e.g. after the account itself is deleted. Unlike
    update_watch_folder, there's no new path to reschedule afterward."""
    if _observer is None:
        return
    with _lock:
        for path_str in list(_watches.get(user_id, {})):
            _unschedule_one(user_id, path_str)
        _watches.pop(user_id, None)
        _primary_folder.pop(user_id, None)
    logger.info("Stopped watching for user %d", user_id)


def update_watch_folder(user_id: int, new_path: Path) -> None:
    """Repoint an already-watched user's PRIMARY folder, e.g. after they
    change it in Settings -- no server restart needed. Any additional
    folders they've separately added keep running, untouched."""
    if _observer is None:
        return
    with _lock:
        old_primary = _primary_folder.get(user_id)
        if old_primary is not None:
            _unschedule_one(user_id, old_primary)
        _schedule(user_id, new_path)
        _primary_folder[user_id] = str(new_path)
    logger.info("Watching %s for user %d", new_path, user_id)
