import hashlib
import logging
import random
import shutil
import time
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as pdf_canvas

from config.settings import settings
from database.db import insert_with_id
from models.models import Document, new_activity_log
from rules.rule_engine import RuleEngine, get_rule_engine, is_within_watch_folder
from services.notification_service import notify
from services.uipath_service import execute_move_via_uipath

UNDOABLE_ACTIONS = ["moved", "renamed_and_moved", "replaced", "archived", "reclassified"]

logger = logging.getLogger("fileflow.organizer")


def is_ignored(path: Path) -> bool:
    if path.suffix.lower() in settings.IGNORED_SUFFIXES:
        return True
    if path.name.startswith("."):
        return True
    # Anything already inside a category/output folder we manage shouldn't
    # be re-processed (the watcher fires on moves within the watch folder).
    return False


def wait_for_stable_file(path: Path) -> bool:
    """Poll file size until it stops changing (download finished)."""
    deadline = time.time() + settings.STABILITY_TIMEOUT
    last_size = -1
    while time.time() < deadline:
        if not path.exists():
            return False
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size == last_size:
            return True
        last_size = size
        time.sleep(settings.STABILITY_POLL_INTERVAL)
    return path.exists()


def compute_hash(path: Path, chunk_size: int = 65536) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_final_name(original_name: str, category: str, engine: RuleEngine) -> str:
    if engine.should_timestamp_rename(category):
        stem = Path(original_name).stem
        suffix = Path(original_name).suffix
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        return f"{ts}_{stem}{suffix}"
    return original_name


def resolve_destination(
    dest_folder: Path, filename: str, source_path: Path, engine: RuleEngine
):
    """Return (destination_path_or_None, action). None destination means
    the file should be left where it is (a duplicate, under "skip" or
    "rename" mode with an identical match)."""
    dest_path = dest_folder / filename
    if not dest_path.exists():
        return dest_path, "moved"

    mode = engine.rules.get("duplicate_handling", "rename")

    if mode == "skip":
        return None, "duplicate_skipped"

    if mode == "replace":
        return dest_path, "replaced"

    # mode == "rename" (default): identical content is skipped, a genuine
    # name collision with different content gets a " (n)" suffix.
    if compute_hash(source_path) == compute_hash(dest_path):
        return None, "duplicate_skipped"

    stem, suffix = Path(filename).stem, Path(filename).suffix
    counter = 1
    while True:
        candidate = dest_folder / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate, "renamed_and_moved"
        counter += 1


def process_file(source_path: Path, db, user: dict) -> Document | None:
    """Classify, dedupe, rename and move a single downloaded file within
    one user's own watch folder. Returns the created activity log
    document, or None if the file was skipped."""
    if is_ignored(source_path):
        return None

    if not wait_for_stable_file(source_path):
        logger.info("File disappeared before it stabilized: %s", source_path)
        return None

    watch_root = Path(user["watch_folder"])
    engine = get_rule_engine(db, user["id"], watch_root)

    file_size = source_path.stat().st_size
    category = engine.classify(source_path.name, file_size)
    dest_folder = watch_root / category
    dest_folder.mkdir(parents=True, exist_ok=True)

    final_name = build_final_name(source_path.name, category, engine)
    dest_path, action = resolve_destination(dest_folder, final_name, source_path, engine)

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
        shutil.move(str(source_path), str(dest_path))

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
    """One-time sweep of files already sitting loose in the user's watch
    folder root (i.e. downloaded before FileFlow started watching). Only
    scans the top level -- it never descends into category subfolders
    FileFlow itself created, so already-organized files are left alone."""
    scanned = organized = duplicates = errors = 0

    watch_root = Path(user["watch_folder"])
    candidates = [p for p in watch_root.iterdir() if p.is_file()]
    for path in candidates:
        if is_ignored(path):
            continue
        scanned += 1
        try:
            log = process_file(path, db, user)
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


def _write_demo_pdf(path: Path, title: str, body: str) -> None:
    """A real, openable PDF -- not just text with a .pdf extension slapped
    on it, which real PDF viewers correctly refuse to open."""
    c = pdf_canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 720, title)
    c.setFont("Helvetica", 11)
    c.drawString(72, 694, body)
    c.drawString(72, 678, f"Created {datetime.now().isoformat()}")
    c.showPage()
    c.save()


def create_simulated_download(user: dict) -> str:
    """Drop a small demo file into the user's watch folder root so the
    live pipeline (already running) picks it up and organizes it -- lets a
    demo show the real detect -> classify -> move flow without waiting for
    an actual download."""
    name_template, content = random.choice(_SIMULATED_FILE_TEMPLATES)
    n = datetime.now().strftime("%H%M%S")
    filename = f"FileFlow_Demo_{name_template.format(n=n)}"
    path = Path(user["watch_folder"]) / filename
    if path.suffix.lower() == ".pdf":
        _write_demo_pdf(path, filename, content)
    else:
        path.write_text(f"{content}\nCreated {datetime.now().isoformat()}\n")
    logger.info("Simulated download created: %s", path)
    return filename


def undo_last_operation(db, user: dict) -> tuple[bool, str, Document | None]:
    raw = db.activity_log.find_one(
        {"user_id": user["id"], "undone": False, "action": {"$in": UNDOABLE_ACTIONS}},
        sort=[("_id", -1)],
    )
    if not raw or not raw.get("destination_path"):
        return False, "No undoable operation found.", None
    log = Document(raw)

    dest = Path(log.destination_path)
    source = Path(log.source_path)
    if not dest.exists():
        return False, f"File no longer exists at {dest}.", None

    source.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        return False, f"Cannot undo: a file already exists at {source}.", None

    shutil.move(str(dest), str(source))
    db.activity_log.update_one({"_id": log["_id"]}, {"$set": {"undone": True}})
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
    dest_path, action = resolve_destination(dest_folder, source.name, source, engine)
    if dest_path is None:
        return (
            False,
            f"An identical file already exists in {category} -- nothing to move.",
            None,
        )

    if action == "replaced" and dest_path.exists():
        dest_path.unlink()

    shutil.move(str(source), str(dest_path))

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
