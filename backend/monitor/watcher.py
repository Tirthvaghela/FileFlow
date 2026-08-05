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
_watches: dict[int, object] = {}


def _schedule(user_id: int, watch_root: Path) -> None:
    handler = DownloadHandler(_loop, _broadcast, _db, user_id, watch_root)
    watch = _observer.schedule(handler, str(watch_root), recursive=True)
    _watches[user_id] = watch


def start_watcher(loop: asyncio.AbstractEventLoop, broadcast, db=None) -> Observer:
    """Start watching every already-registered user's folder. New accounts
    get added live afterward via add_user_watch(), no restart needed."""
    global _observer, _loop, _broadcast, _db
    _loop = loop
    _broadcast = broadcast
    _db = db if db is not None else default_db

    observer = Observer()
    _observer = observer
    for user in _db.users.find():
        watch_folder = user.get("watch_folder")
        if not watch_folder:
            logger.warning(
                "Skipping user %r -- no watch_folder on record.", user.get("email")
            )
            continue
        _schedule(user["id"], Path(watch_folder))
    observer.start()
    logger.info("Watching %d user folder(s)", len(_watches))
    return observer


def add_user_watch(user_id: int, watch_root: Path) -> None:
    """Start watching a newly-registered user's folder on the
    already-running observer."""
    if _observer is None:
        return
    _schedule(user_id, watch_root)
    logger.info("Watching %s for user %d", watch_root, user_id)


def update_watch_folder(user_id: int, new_path: Path) -> None:
    """Repoint an already-watched user at a new folder, e.g. after they
    change it in Settings -- no server restart needed."""
    if _observer is None:
        return
    old_watch = _watches.get(user_id)
    if old_watch is not None:
        _observer.unschedule(old_watch)
    _schedule(user_id, new_path)
    logger.info("Watching %s for user %d", new_path, user_id)
