"""Watches this machine's real local folder and organizes files into it --
the agent-side counterpart to backend/monitor/watcher.py, reusing the exact
same pure classification/dedupe helpers so behavior matches the
single-machine mode exactly, just executed here instead of on the backend.
"""

import logging
import threading
import uuid
from pathlib import Path

import requests
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from automation.file_ops import (
    build_final_name,
    compute_hash,
    is_ignored,
    resolve_destination,
    wait_for_stable_file,
)
from rules.classifier import classify_file_explained
from services.notification_service import notify
from services.uipath_service import execute_move_via_uipath

from agent import outbox, rules_cache

logger = logging.getLogger("fileflow.agent.watcher")

# Same rationale as organizer.py's _move_lock: two files landing in the same
# watchdog tick can both pass resolve_destination()'s exists() check for the
# same computed destination before either has actually moved anything.
# Shared with commands.py's reclassify handling, which moves files within
# this same watched folder.
move_lock = threading.Lock()

# commands.py's undo/reclassify handlers move a file FROM a category
# subfolder back to (or across) the watch root -- that move is itself a
# filesystem event this same watcher observes. Unlike a move INTO a
# subfolder (already guarded below), a move landing back at the top level
# looks exactly like a brand-new download, so without this the watcher
# would immediately re-organize an undo right back into the folder it was
# just undone from. commands.py calls mark_self_move() with the
# destination path right before performing that move; the very next event
# for that exact path is consumed here instead of triggering a reprocess.
_self_moves: set[Path] = set()
_self_moves_lock = threading.Lock()


def mark_self_move(path: Path) -> None:
    with _self_moves_lock:
        _self_moves.add(path.resolve())


def unmark_self_move(path: Path) -> None:
    """Cancels a mark_self_move() whose rename never actually happened (the
    OS-level move that was about to follow it raised instead). Without this,
    a failed undo would leave a stale marker behind, and _consume_self_move()
    has no way to distinguish "we moved it" from "we only intended to" -- the
    very next legitimate download landing at that exact path would be
    silently swallowed instead of organized."""
    _consume_self_move(path)


def _consume_self_move(path: Path) -> bool:
    with _self_moves_lock:
        resolved = path.resolve()
        if resolved in _self_moves:
            _self_moves.discard(resolved)
            return True
    return False


class AgentDownloadHandler(FileSystemEventHandler):
    def __init__(self, client, watch_root: Path, outbox_conn):
        super().__init__()
        self.client = client
        self.watch_root = watch_root
        self.outbox_conn = outbox_conn
        # Two independent reasons watching can be paused -- the tray
        # icon's "Pause watching" menu item, and the website's "Real-time
        # monitoring" toggle (synced in by poll_forever, see
        # commands.py). Kept separate rather than one shared flag so
        # neither source can silently override the other: pausing from
        # the tray while the website still has monitoring on shouldn't
        # un-pause on the next sync, and vice versa. Plain bools (no
        # lock/Event needed) are fine here too -- same reasoning as
        # before, just twice.
        self.manually_paused = False
        self.remote_monitoring_disabled = False

    @property
    def paused(self) -> bool:
        return self.manually_paused or self.remote_monitoring_disabled

    def on_created(self, event):
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def on_moved(self, event):
        if not event.is_directory:
            self._handle(Path(event.dest_path))

    def _handle(self, path: Path):
        if self.paused:
            return
        # A move INTO a category subfolder this agent itself created is our
        # own doing, not a new download -- same guard the backend watcher
        # uses (monitor/watcher.py::_is_inside_managed_subfolder).
        try:
            relative = path.relative_to(self.watch_root)
        except ValueError:
            return
        if len(relative.parts) > 1:
            return
        if _consume_self_move(path):
            return
        threading.Thread(target=self._process, args=(path,), daemon=True).start()

    def _process(self, path: Path):
        try:
            process_download(self.client, self.watch_root, self.outbox_conn, path)
        except requests.exceptions.RequestException:
            outbox.enqueue_pending_file(self.outbox_conn, path)
            logger.info("Backend unreachable -- %s queued for retry", path)
        except Exception:
            logger.exception("Failed to process %s", path)


def process_download(client, watch_root: Path, outbox_conn, path: Path) -> None:
    """Classify, dedupe, rename and move one file. Shared by the live
    watchdog handler above and commands.py's retry_pending_files, so a
    file that couldn't be reached the first time (backend down) is
    processed identically on retry, not by a second, drifting code path.
    Raises requests.exceptions.RequestException if the backend can't be
    reached at all (no cached rules to fall back on either) -- callers
    decide what to do with that; everything else is handled here."""
    if is_ignored(path):
        return
    if not wait_for_stable_file(path):
        logger.info("File disappeared or never stabilized: %s", path)
        return

    rules = rules_cache.get_rules(client)
    file_size = path.stat().st_size
    explanation = classify_file_explained(rules, path.name, file_size, watch_root, file_path=path)
    category = explanation["destination"]
    dest_folder = watch_root / category
    dest_folder.mkdir(parents=True, exist_ok=True)

    with move_lock:
        final_name = build_final_name(path.name, category, rules)
        dest_path, action = resolve_destination(dest_folder, final_name, path, rules)
        file_hash = compute_hash(path)

        if action == "duplicate_skipped":
            outbox.enqueue_activity(
                outbox_conn,
                original_filename=path.name,
                final_filename=path.name,
                source_path=str(path),
                destination_path=None,
                category=category,
                action=action,
                file_size=file_size,
                file_hash=file_hash,
                client_ref=str(uuid.uuid4()),
                explanation=explanation,
            )
            notify("Duplicate Skipped", f"{path.name} already exists in {category}", rules)
            return

        if action == "replaced" and dest_path.exists():
            dest_path.unlink()

        if execute_move_via_uipath(path, dest_path.parent, dest_path.name) is None:
            # See the equivalent guard in backend/automation/organizer.py's
            # process_file: a Robot that actually completed the move but
            # failed to *report* it cleanly (non-zero exit, bad output)
            # returns None just like one that never ran at all -- rename()
            # would raise on the now-missing source in that case, losing
            # this activity report even though the file is really there.
            if path.exists() or not dest_path.exists():
                path.rename(dest_path)

    outbox.enqueue_activity(
        outbox_conn,
        original_filename=path.name,
        final_filename=dest_path.name,
        source_path=str(path),
        destination_path=str(dest_path),
        category=category,
        action=action,
        file_size=file_size,
        file_hash=file_hash,
        client_ref=str(uuid.uuid4()),
        explanation=explanation,
    )
    notify("File Organized Successfully", f"{dest_path.name} moved to {category}", rules)
    logger.info("Organized %s -> %s", path.name, dest_path)


def start_watching(client, watch_root: Path, outbox_conn) -> tuple[Observer, AgentDownloadHandler]:
    watch_root.mkdir(parents=True, exist_ok=True)
    handler = AgentDownloadHandler(client, watch_root, outbox_conn)
    observer = Observer()
    observer.schedule(handler, str(watch_root), recursive=True)
    observer.start()
    logger.info("Watching %s", watch_root)
    return observer, handler
