"""Pure classification logic -- no database, no RuleEngine instance needed.

Extracted out of RuleEngine so the exact same classification behavior is
usable by something that only has a plain rules dict (fetched over the API)
and no Mongo connection at all, namely the remote agent. RuleEngine itself
becomes a thin, DB-backed wrapper around these two functions.
"""

import logging
import re
import time
from pathlib import Path

logger = logging.getLogger("fileflow.rules")

# Enough to catch a keyword near the top of a real text/office document
# without reading an entire large or binary file into memory just to
# classify it.
_CONTENT_SNIFF_MAX_BYTES = 64 * 1024


def _read_content_snippet(file_path: Path) -> str | None:
    try:
        with open(file_path, "rb") as f:
            raw = f.read(_CONTENT_SNIFF_MAX_BYTES)
    except OSError:
        return None
    # errors="ignore" rather than a stricter codec: this runs on arbitrary
    # user files, including binary ones (images, archives) that were never
    # meant to be decoded as text at all -- best-effort keyword matching on
    # whatever comes through beats raising over a file that's simply not
    # UTF-8 text.
    return raw.decode("utf-8", errors="ignore").lower()


def is_within_watch_folder(folder: str, watch_root: Path) -> bool:
    """A destination folder (name or absolute path) must resolve to
    somewhere inside a user's own watch folder -- shared by anything that
    writes based on rules config (this module's classify_file(), and the
    archive scheduler), so a typo'd or malicious value never causes a
    file to be moved outside the tree that user's FileFlow instance was
    told to manage."""
    try:
        root = watch_root.resolve()
        candidate = (watch_root / folder).resolve()
    except (OSError, ValueError):
        return False
    return candidate == root or root in candidate.parents


def classify_file(
    rules: dict,
    filename: str,
    file_size_bytes: int,
    watch_root: Path,
    file_path: Path | None = None,
) -> str:
    """Return the destination folder name for a given file.

    file_path is optional and only needed for the two rule types that
    require touching the actual file (date_rules reads its mtime,
    content_keyword_rules reads its bytes) -- every caller that only has a
    bare filename (existing tests, a dry-run preview) can omit it and those
    two rule types simply never match, exactly as if they were unset."""
    name_lower = filename.lower()
    ext = Path(filename).suffix.lower()

    def validated(folder: str) -> str | None:
        if is_within_watch_folder(folder, watch_root):
            return folder
        logger.warning("Ignoring rule destination outside the watch folder: %r", folder)
        return None

    for rule in rules.get("keyword_rules", []):
        if rule["keyword"].lower() in name_lower:
            folder = validated(rule["folder"])
            if folder:
                return folder

    for rule in rules.get("regex_rules", []):
        try:
            matched = re.search(rule["pattern"], filename, re.IGNORECASE)
        except re.error:
            logger.warning("Skipping invalid regex rule pattern: %r", rule["pattern"])
            continue
        if matched:
            folder = validated(rule["folder"])
            if folder:
                return folder

    content_rules = rules.get("content_keyword_rules", [])
    if content_rules and file_path is not None:
        snippet = _read_content_snippet(file_path)
        if snippet is not None:
            for rule in content_rules:
                if rule["keyword"].lower() in snippet:
                    folder = validated(rule["folder"])
                    if folder:
                        return folder

    extension_rules = rules.get("extension_rules", {})
    if ext in extension_rules:
        folder = validated(extension_rules[ext])
        if folder:
            return folder

    threshold_mb = rules.get("large_file_threshold_mb")
    if (
        rules.get("large_file_enabled", True)
        and threshold_mb
        and file_size_bytes > threshold_mb * 1024 * 1024
    ):
        folder = validated(rules.get("large_file_folder", "Large Files"))
        if folder:
            return folder

    if file_path is not None:
        for rule in rules.get("date_rules", []):
            try:
                age_days = (time.time() - file_path.stat().st_mtime) / 86400
            except OSError:
                continue
            if age_days >= rule["older_than_days"]:
                folder = validated(rule["folder"])
                if folder:
                    return folder

    for category, extensions in rules.get("categories", {}).items():
        if ext in extensions:
            return validated(category) or "Others"

    if ext and rules.get("auto_organize_unknown_extensions", True):
        auto_folder = f"{ext[1:].upper()} Files"
        folder = validated(auto_folder)
        if folder:
            return folder

    return validated(rules.get("default_category", "Others")) or "Others"


def should_timestamp_rename(rules: dict, category: str) -> bool:
    if not rules.get("enable_timestamp_rename", False):
        return False
    return category in rules.get("timestamp_rename_categories", [])
