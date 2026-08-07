import io
import logging
import random
from datetime import datetime
from pathlib import Path

from pymongo import ReturnDocument
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as pdf_canvas

from automation.file_ops import (
    build_final_name,
    compute_hash,
    is_ignored,
    move_lock as _move_lock,
    resolve_destination,
    wait_for_stable_file,
)
from config.settings import all_watch_folders
from database.db import insert_with_id
from models.models import Document, new_activity_log
from rules.classifier import is_within_watch_folder
from rules.rule_engine import get_rule_engine
from services.notification_service import notify
from services.uipath_service import execute_move_via_uipath

UNDOABLE_ACTIONS = ["moved", "renamed_and_moved", "replaced", "archived", "reclassified"]

logger = logging.getLogger("fileflow.organizer")

__all__ = [
    "is_ignored",
    "wait_for_stable_file",
    "compute_hash",
    "build_final_name",
    "resolve_destination",
    "process_file",
    "organize_existing_files",
    "generate_simulated_download",
    "claim_undoable_log",
    "release_undo_claim",
    "undo_last_operation",
    "reclassify_file",
]


def process_file(source_path: Path, db, user: dict) -> Document | None:
    """Classify, dedupe, rename and move a single downloaded file within
    one user's own watch folder. Returns the created activity log
    document, or None if the file was skipped."""
    if is_ignored(source_path):
        return None

    if not wait_for_stable_file(source_path):
        logger.info("File disappeared or never stabilized: %s", source_path)
        return None

    watch_root = Path(user["watch_folder"])
    engine = get_rule_engine(db, user["id"], watch_root)

    file_size = source_path.stat().st_size
    category = engine.classify(source_path.name, file_size, file_path=source_path)
    dest_folder = watch_root / category
    dest_folder.mkdir(parents=True, exist_ok=True)

    # Everything from here on decides a destination and then physically
    # commits to it -- see the _move_lock comment above for why this whole
    # sequence needs to be serialized, not just the final move call.
    with _move_lock:
        final_name = build_final_name(source_path.name, category, engine.rules)
        dest_path, action = resolve_destination(dest_folder, final_name, source_path, engine.rules)

        file_hash = compute_hash(source_path)

        if action == "duplicate_skipped":
            log = insert_with_id(
                db,
                "activity_log",
                new_activity_log(
                    user_id=user["id"],
                    original_filename=source_path.name,
                    final_filename=source_path.name,
                    source_path=str(source_path),
                    destination_path=None,
                    category=category,
                    action=action,
                    file_size=file_size,
                    file_hash=file_hash,
                ),
            )
            notify("Duplicate Skipped", f"{source_path.name} already exists in {category}", engine.rules)
            return Document(log)

        if action == "replaced" and dest_path.exists():
            dest_path.unlink()

        # UiPath Robot performs the physical move when enabled; any failure
        # (disabled, missing Robot, timeout, bad output) falls back to the
        # plain Python move -- organizing a file must never depend on RPA
        # infrastructure being available.
        if execute_move_via_uipath(source_path, dest_path.parent, dest_path.name) is None:
            # .rename(), not shutil.move(): shutil's own fallback silently
            # absorbs a "destination already exists" collision by copying
            # over it instead of raising. Belt-and-suspenders alongside
            # _move_lock above -- the lock is what actually prevents the
            # race; this makes sure a *non*-racing failure (e.g. the OS
            # refusing the rename for an unrelated reason) surfaces as a
            # normal error instead of silently overwriting something.
            source_path.rename(dest_path)

    log = insert_with_id(
        db,
        "activity_log",
        new_activity_log(
            user_id=user["id"],
            original_filename=source_path.name,
            final_filename=dest_path.name,
            source_path=str(source_path),
            destination_path=str(dest_path),
            category=category,
            action=action,
            file_size=file_size,
            file_hash=file_hash,
        ),
    )

    notify("File Organized Successfully", f"{dest_path.name} moved to {category}", engine.rules)
    logger.info("Organized %s -> %s", source_path.name, dest_path)
    return Document(log)


def organize_existing_files(db, user: dict) -> dict:
    """One-time sweep of files already sitting loose in each of the user's
    watch folders' roots (primary plus any additional ones -- see
    config.settings.all_watch_folders) -- i.e. downloaded before FileFlow
    started watching. Only scans each folder's top level -- it never
    descends into category subfolders FileFlow itself created, so
    already-organized files are left alone."""
    scanned = organized = duplicates = errors = 0

    for watch_root in all_watch_folders(user):
        if not watch_root.exists():
            continue
        # process_file() derives its watch_root (containment checks,
        # destination-folder placement) from user["watch_folder"] alone --
        # substituting it per-folder here is what makes a file dropped in
        # an *additional* folder land in that folder's own "Documents"
        # subfolder, not get misfiled relative to the primary folder.
        folder_user = {**user, "watch_folder": str(watch_root)}
        candidates = [p for p in watch_root.iterdir() if p.is_file()]
        for path in candidates:
            if is_ignored(path):
                continue
            scanned += 1
            try:
                log = process_file(path, db, folder_user)
            except Exception:
                logger.exception("Failed to organize existing file %s", path)
                errors += 1
                continue
            if log is None:
                continue
            if log.action == "duplicate_skipped":
                duplicates += 1
            else:
                organized += 1

    return {
        "scanned": scanned,
        "organized": organized,
        "duplicates": duplicates,
        "errors": errors,
    }


_SIMULATED_FILE_TEMPLATES = [
    ("Invoice_{n}.pdf", "Simulated invoice document for demo purposes."),
    ("Report_{n}.pdf", "Simulated report document for demo purposes."),
    ("Notes_{n}.txt", "Simulated text note for demo purposes."),
    ("Photo_{n}.jpg", "Simulated image bytes for demo purposes."),
    ("script_{n}.py", "print('Simulated download for demo purposes.')"),
    ("Presentation_{n}.pptx", "Simulated slide deck for demo purposes."),
]


def _demo_pdf_bytes(title: str, body: str) -> bytes:
    """A real, openable PDF -- not just text with a .pdf extension slapped
    on it, which real PDF viewers correctly refuse to open."""
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 720, title)
    c.setFont("Helvetica", 11)
    c.drawString(72, 694, body)
    c.drawString(72, 678, f"Created {datetime.now().isoformat()}")
    c.showPage()
    c.save()
    return buffer.getvalue()


_SIMULATED_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".jpg": "image/jpeg",
    ".py": "text/x-python",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def generate_simulated_download() -> tuple[str, bytes, str]:
    """Build a small demo file's bytes for the browser to download for real,
    instead of writing straight into the watch folder from the backend
    process. A genuine OS-level download lands wherever the browser saves
    downloads -- typically the same folder FileFlow is already watching --
    so the live pipeline picks it up exactly like any real download would."""
    name_template, content = random.choice(_SIMULATED_FILE_TEMPLATES)
    n = datetime.now().strftime("%H%M%S")
    filename = f"FileFlow_Demo_{name_template.format(n=n)}"
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        data = _demo_pdf_bytes(filename, content)
    else:
        data = f"{content}\nCreated {datetime.now().isoformat()}\n".encode()
    media_type = _SIMULATED_MEDIA_TYPES.get(suffix, "application/octet-stream")
    return filename, data, media_type


def claim_undoable_log(db, user_id: int) -> Document | None:
    """Atomically claim the most recent undoable row (flip undone -> True)
    BEFORE touching the filesystem, instead of a plain find_one + later
    update_one. Two concurrent undo calls (a double-click, or a retried
    request) used to both read the same row while it was still
    undone=False, both pass the exists() checks in undo_last_operation,
    and race to shutil.move() the same file -- the loser's move raised
    straight out of the request as a 500. Mongo's find_one_and_update
    only ever lets ONE caller win that race; the other naturally falls
    through to the next-most-recent undoable row (or None), never
    touching the file at all.

    Extracted out of undo_last_operation so the claim itself can also be
    used by the agent-connected path (api/routes.py), which queues the
    actual move for the agent to perform instead of doing it locally --
    the claim's concurrency guarantee has to hold either way."""
    raw = db.activity_log.find_one_and_update(
        {"user_id": user_id, "undone": False, "action": {"$in": UNDOABLE_ACTIONS}},
        {"$set": {"undone": True}},
        sort=[("_id", -1)],
        return_document=ReturnDocument.BEFORE,
    )
    if not raw or not raw.get("destination_path"):
        return None
    return Document(raw)


def release_undo_claim(db, log_id: int) -> None:
    """Undo the claim itself -- for when the claimed row turns out not to
    be actionable after all (file gone, destination collision, or -- for
    the agent-connected path -- the agent reports the move-back failed)."""
    db.activity_log.update_one({"_id": log_id}, {"$set": {"undone": False}})


def undo_last_operation(db, user: dict) -> tuple[bool, str, Document | None]:
    log = claim_undoable_log(db, user["id"])
    if log is None:
        return False, "No undoable operation found.", None

    dest = Path(log.destination_path)
    source = Path(log.source_path)

    # Same _move_lock as process_file/reclassify_file: the Mongo claim above
    # already keeps two undo calls for the *same row* from double-moving,
    # but it can't stop this undo's destination path from colliding with a
    # totally different row's concurrent process_file/reclassify move --
    # only a shared lock around every "check exists, then move" sequence
    # closes that.
    with _move_lock:
        if not dest.exists():
            # Already claimed, but there's no file work to do -- release the
            # claim so this row stays visible as undoable for a future attempt
            # rather than silently vanishing from history.
            release_undo_claim(db, log["_id"])
            return False, f"File no longer exists at {dest}.", None

        source.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            release_undo_claim(db, log["_id"])
            return False, f"Cannot undo: a file already exists at {source}.", None

        try:
            # .rename(), not shutil.move(): see the comment on the equivalent
            # call in process_file() -- a plain shutil.move() would silently
            # absorb a genuine destination collision via its own copy+overwrite
            # fallback instead of raising.
            dest.rename(source)
        except OSError as exc:
            release_undo_claim(db, log["_id"])
            return False, f"Could not restore {log.final_filename}: {exc}", None

    log.undone = True
    return True, f"Restored {log.final_filename} to its original location.", log


def reclassify_file(
    log_id: int, new_category: str, db, user: dict
) -> tuple[bool, str, Document | None]:
    """Manually move an already-organized file to a different category --
    the fix for a rule that got it wrong. Logged as its own 'reclassified'
    action (undoable via the normal undo endpoint), never touching the
    original log row so the audit trail stays intact. Scoped to the
    acting user's own logs -- one account can never reclassify another
    account's file."""
    raw = db.activity_log.find_one({"_id": log_id, "user_id": user["id"]})
    if not raw:
        return False, "That entry can't be reclassified.", None
    log = Document(raw)
    if log.undone or not log.destination_path:
        return False, "That entry can't be reclassified.", None

    source = Path(log.destination_path)
    if not source.exists():
        return False, f"File no longer exists at {source}.", None

    watch_root = Path(user["watch_folder"])
    category = new_category.strip()
    if not category or not is_within_watch_folder(category, watch_root):
        return False, "Invalid destination category.", None

    dest_folder = watch_root / category
    dest_folder.mkdir(parents=True, exist_ok=True)

    engine = get_rule_engine(db, user["id"], watch_root)

    # Same _move_lock as process_file/undo_last_operation. Nothing
    # atomically "claims" this log row the way undo does, so two concurrent
    # reclassify calls for the same entry (double-click, or a retried
    # request) both used to pass resolve_destination()'s exists() check and
    # both "succeed" -- verified directly: both reported success and both
    # logged as having moved the file, with only one copy actually
    # surviving on disk, because .rename()'s own collision check isn't
    # exclusive against another thread's concurrent rename to that same
    # target. Holding the lock across resolve + move makes the two steps
    # atomic as a pair instead of two independently-racy checks.
    with _move_lock:
        try:
            # resolve_destination() itself reads/hashes `source` (for the
            # duplicate-content check) before anything moves -- if a
            # concurrent reclassify of this same entry already won the lock
            # and moved the file away, that read fails with FileNotFoundError
            # here, not just in the rename below, so it needs the same
            # graceful handling rather than being allowed to propagate.
            dest_path, action = resolve_destination(dest_folder, source.name, source, engine.rules)
        except OSError:
            logger.warning("Reclassify race: %s vanished before it could be reclassified", source)
            return False, f"File no longer exists at {source}.", None

        if dest_path is None:
            return (
                False,
                f"An identical file already exists in {category} -- nothing to move.",
                None,
            )

        if action == "replaced" and dest_path.exists():
            dest_path.unlink()

        try:
            # .rename(), not shutil.move(): shutil's own fallback silently
            # absorbs a "destination already exists" collision by copying
            # over it instead of raising.
            source.rename(dest_path)
        except OSError:
            logger.warning("Reclassify race: %s vanished before the move completed", source)
            return False, f"File no longer exists at {source}.", None

    new_log = insert_with_id(
        db,
        "activity_log",
        new_activity_log(
            user_id=user["id"],
            original_filename=log.original_filename,
            final_filename=dest_path.name,
            source_path=str(source),
            destination_path=str(dest_path),
            category=category,
            action="reclassified",
            file_size=log.file_size,
            file_hash=log.file_hash,
        ),
    )
    return True, f"Moved {dest_path.name} to {category}.", Document(new_log)