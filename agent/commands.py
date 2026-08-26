"""Polls the backend for pending commands (undo / reclassify /
organize_existing) that only this agent can actually carry out, since it's
the one with real filesystem access to the watched folder."""

import json
import logging
import os
import time
import uuid
from pathlib import Path

import requests

from automation.file_ops import (
    build_final_name,
    compute_hash,
    is_ignored,
    resolve_destination,
    wait_for_stable_file,
)
from rules.classifier import classify_file
from services.notification_service import notify
from services.uipath_service import execute_move_via_uipath

from agent import outbox, rules_cache, updater
from agent.watcher import mark_self_move, move_lock, process_download, unmark_self_move

logger = logging.getLogger("fileflow.agent.commands")

POLL_INTERVAL_SECONDS = 5
MAX_POLL_BACKOFF_SECONDS = 60
# Update checks are deliberately much less frequent than the command poll
# -- there's no urgency (this isn't a security patch delivery mechanism)
# and hitting the backend for a version check every 5 seconds forever
# would be wasteful.
UPDATE_CHECK_INTERVAL_SECONDS = 6 * 60 * 60


def _do_undo(payload: dict) -> tuple[bool, str | None]:
    dest_str = payload.get("destination_path")
    dest = Path(dest_str) if dest_str else None
    source = Path(payload["source_path"])

    with move_lock:
        if dest is None or not dest.exists():
            return False, f"File no longer exists at {dest}."
        if source.exists():
            return False, f"A file already exists at {source}."
        try:
            source.parent.mkdir(parents=True, exist_ok=True)
            # Moving back to the watch root looks exactly like a new
            # download to the watcher -- mark it first so it's ignored
            # instead of immediately re-organized right back where it
            # came from.
            mark_self_move(source)
            dest.rename(source)
        except OSError as exc:
            # The rename never happened -- undo the mark_self_move() above
            # too, or the next real download landing at this exact path
            # would be silently swallowed by a marker for a move that
            # never actually occurred.
            unmark_self_move(source)
            return False, str(exc)
    return True, None


def _do_reclassify(client, watch_root: Path, payload: dict) -> tuple[bool, str | None, dict]:
    source = Path(payload["source_path"])
    category = payload["category"]
    if not source.exists():
        return False, f"File no longer exists at {source}.", {}

    rules = rules_cache.get_rules(client)
    dest_folder = watch_root / category
    dest_folder.mkdir(parents=True, exist_ok=True)

    with move_lock:
        try:
            dest_path, action = resolve_destination(dest_folder, source.name, source, rules)
        except OSError as exc:
            return False, str(exc), {}
        if dest_path is None:
            return False, f"An identical file already exists in {category}.", {}
        if action == "replaced" and dest_path.exists():
            dest_path.unlink()
        try:
            source.rename(dest_path)
        except OSError as exc:
            return False, str(exc), {}

    return True, None, {"destination_path": str(dest_path)}


def _do_organize_existing(client, watch_root: Path, outbox_conn) -> dict:
    scanned = organized = duplicates = errors = 0
    for path in [p for p in watch_root.iterdir() if p.is_file()]:
        if is_ignored(path):
            continue
        scanned += 1
        try:
            if not wait_for_stable_file(path):
                continue
            rules = rules_cache.get_rules(client)
            file_size = path.stat().st_size
            category = classify_file(rules, path.name, file_size, watch_root, file_path=path)
            dest_folder = watch_root / category
            dest_folder.mkdir(parents=True, exist_ok=True)

            with move_lock:
                final_name = build_final_name(path.name, category, rules)
                dest_path, action = resolve_destination(dest_folder, final_name, path, rules)
                file_hash = compute_hash(path)

                if action == "duplicate_skipped":
                    duplicates += 1
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
                    )
                    continue

                if action == "replaced" and dest_path.exists():
                    dest_path.unlink()
                if execute_move_via_uipath(path, dest_path.parent, dest_path.name) is None:
                    # See the equivalent guard in watcher.py's
                    # process_download / organizer.py's process_file: a
                    # Robot that actually completed the move but failed to
                    # *report* it cleanly looks identical to one that never
                    # ran, and rename() would raise on the now-missing
                    # source in that case.
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
            )
            organized += 1
        except Exception:
            logger.exception("Failed to organize existing file %s", path)
            errors += 1

    return {"scanned": scanned, "organized": organized, "duplicates": duplicates, "errors": errors}


def _handle(client, watch_root: Path, command: dict, outbox_conn) -> None:
    """Computes the command's result exactly once, then durably queues the
    completion report -- delivering that report is retried by
    flush_outbox(), but the action itself (which may have already moved a
    real file) never runs a second time just because reporting failed.

    That "exactly once" only held within a single call until this guard
    existed: the backend only stops redelivering a command once it durably
    receives a completion report, so a command whose first report is still
    queued locally (backend briefly unreachable, or just hasn't been
    flushed yet this cycle) would otherwise get handed to this function
    again by the next poll cycle -- running undo/reclassify/organize-
    existing a second time for real, not just retrying the report."""
    if outbox.has_pending_completion(outbox_conn, command["id"]):
        return
    command_type = command["type"]
    payload = command["payload"]
    result: dict | None = None
    try:
        if command_type == "undo":
            success, error = _do_undo(payload)
        elif command_type == "reclassify":
            success, error, result = _do_reclassify(client, watch_root, payload)
        elif command_type == "organize_existing":
            result = _do_organize_existing(client, watch_root, outbox_conn)
            success, error = True, None
        else:
            logger.warning("Unknown command type: %s", command_type)
            return
    except Exception as exc:
        logger.exception("Command %s failed", command["id"])
        success, error = False, str(exc)
    outbox.enqueue_command_complete(outbox_conn, command["id"], success, error, result)


def retry_pending_files(client, watch_root: Path, outbox_conn) -> bool:
    """Re-attempts each file that couldn't be reached the first time
    (backend was down when it landed). Returns False the moment a
    connection error recurs, so poll_forever can back off instead of
    hammering every file in the queue against a backend that's still
    unreachable."""
    for row in outbox.due_items(outbox_conn, "pending_file"):
        path = Path(json.loads(row["payload"])["path"])
        if not path.exists():
            outbox.delete_item(outbox_conn, row["id"])
            continue
        try:
            process_download(client, watch_root, outbox_conn, path)
            outbox.delete_item(outbox_conn, row["id"])
        except requests.exceptions.RequestException:
            outbox.bump_failure(outbox_conn, row["id"])
            return False
        except Exception:
            logger.exception("Giving up retrying %s", path)
            outbox.delete_item(outbox_conn, row["id"])
    return True


def poll_forever(
    client, watch_root: Path, outbox_conn, on_before_update_exit=None, get_handler=None, get_watch_root=None
) -> None:
    backoff = POLL_INTERVAL_SECONDS
    next_update_check = 0.0
    while True:
        healthy = True
        try:
            # Re-resolved every iteration, like get_handler() just below --
            # a Reconfigure that changes the watch folder mid-run must not
            # leave the rest of this thread's life operating against the
            # folder it happened to be started with. Without this,
            # reclassify/organize_existing commands (and pending-file
            # retries) kept computing destinations against the OLD folder
            # forever, even after the handler/observer had already
            # correctly swapped to the new one.
            current_watch_root = get_watch_root() if get_watch_root is not None else watch_root
            outbox.flush_outbox(client, outbox_conn)
            if not retry_pending_files(client, current_watch_root, outbox_conn):
                healthy = False
            for command in client.get_commands():
                _handle(client, current_watch_root, command, outbox_conn)

            # Syncs the website's "Real-time monitoring" toggle into the
            # live watcher every cycle -- get_handler() (not a handler
            # passed once at thread-start) so this keeps working across a
            # Reconfigure that swaps in a brand new handler object.
            if get_handler is not None:
                handler = get_handler()
                if handler is not None:
                    rules = rules_cache.get_rules(client)
                    handler.remote_monitoring_disabled = not rules.get(
                        "realtime_monitoring_enabled", True
                    )

            if time.time() >= next_update_check:
                next_update_check = time.time() + UPDATE_CHECK_INTERVAL_SECONDS
                manifest = updater.check_for_update(client)
                if manifest and updater.download_and_apply(client, manifest):
                    notify(
                        "FileFlow Agent Updating",
                        f"Updating to version {manifest['version']} -- "
                        "restarting automatically.",
                        {},
                    )
                    if on_before_update_exit:
                        on_before_update_exit()
                    # A hard process exit, not sys.exit(): this runs on the
                    # poller's own daemon thread, and the main thread's
                    # blocking pystray loop needs to end too so the
                    # installer we just launched can overwrite this
                    # process's own files a moment from now.
                    os._exit(0)
        except requests.exceptions.RequestException:
            healthy = False
        except Exception:
            logger.exception("Command poll failed")

        if healthy:
            backoff = POLL_INTERVAL_SECONDS
        else:
            logger.warning("Backend unreachable, retrying in %ss", backoff)
            backoff = min(backoff * 2, MAX_POLL_BACKOFF_SECONDS)
        time.sleep(backoff)
