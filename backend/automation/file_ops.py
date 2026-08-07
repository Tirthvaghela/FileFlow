"""Pure, dependency-light file operations shared by the backend's local
watcher and the remote agent (agent/watcher.py, agent/commands.py). Kept
separate from organizer.py specifically so the agent -- which gets
packaged into a standalone .exe -- never has to bundle organizer.py's
pymongo/reportlab imports, which it never actually calls. Same reasoning
that already split rules/classifier.py out of rules/rule_engine.py."""

import hashlib
import threading
import time
from datetime import datetime
from pathlib import Path

from config.settings import settings
from rules.classifier import should_timestamp_rename

# Guards every "decide a destination, then physically move a file there"
# sequence in organizer.py/agent watcher/agent commands. Verified directly
# (not just theorized): two threads can both pass resolve_destination()'s
# exists() check for the same destination AND both have their
# Path.rename() call report success -- on Windows, a rename's own "does
# the target already exist" check is not exclusive against another
# thread's concurrent rename to that same target, so filesystem atomicity
# alone isn't a strong enough guarantee here. A single process-wide lock
# is a deliberately simple, fully-correct trade: file organizing is not a
# high-throughput path (a handful of files a second at the very most), so
# serializing every move across every user costs nothing a real user
# would notice, in exchange for never silently losing a file to a lost
# race.
move_lock = threading.Lock()


def is_ignored(path: Path) -> bool:
    if path.suffix.lower() in settings.IGNORED_SUFFIXES:
        return True
    if path.name.startswith("."):
        return True
    # Anything already inside a category/output folder we manage shouldn't
    # be re-processed (the watcher fires on moves within the watch folder).
    return False


def wait_for_stable_file(path: Path) -> bool:
    """Poll file size until it stops changing (download finished). A file
    that's still growing on every single poll when the timeout hits is NOT
    stable -- moving/hashing it mid-write would capture a truncated size
    and content. Give up and let it be picked up on a later pass (e.g. a
    manual "organize existing files" sweep) instead of treating "still
    exists" as "finished downloading"."""
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
    return False


def compute_hash(path: Path, chunk_size: int = 65536) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_final_name(original_name: str, category: str, rules: dict) -> str:
    if should_timestamp_rename(rules, category):
        stem = Path(original_name).stem
        suffix = Path(original_name).suffix
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        return f"{ts}_{stem}{suffix}"
    return original_name


def resolve_destination(
    dest_folder: Path, filename: str, source_path: Path, rules: dict
):
    """Return (destination_path_or_None, action). None destination means
    the file should be left where it is (a duplicate, under "skip" or
    "rename" mode with an identical match)."""
    dest_path = dest_folder / filename
    if not dest_path.exists():
        return dest_path, "moved"

    mode = rules.get("duplicate_handling", "rename")

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
