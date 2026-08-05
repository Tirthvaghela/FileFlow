import json
import logging
import threading
from pathlib import Path

from config.settings import settings

_lock = threading.Lock()
logger = logging.getLogger("fileflow.rules")

# Test-only seam: when set, get_rule_engine() returns this instance for
# every caller (routes, organizer, watcher, archive scheduler) instead of
# constructing a real per-user one -- lets tests freely mutate one shared
# `rules` dict via the `test_rules` fixture. Always None in production.
_test_engine_override: "RuleEngine | None" = None


def is_within_watch_folder(folder: str, watch_root: Path) -> bool:
    """A destination folder (name or absolute path) must resolve to
    somewhere inside a user's own watch folder -- shared by anything that
    writes based on rules config (the rule engine's classify() path, and
    the archive scheduler), so a typo'd or malicious value never causes a
    file to be moved outside the tree that user's FileFlow instance was
    told to manage."""
    try:
        root = watch_root.resolve()
        candidate = (watch_root / folder).resolve()
    except (OSError, ValueError):
        return False
    return candidate == root or root in candidate.parents


def _load_default_template() -> dict:
    """The on-disk rules.json is a read-only seed template -- it's read
    once to seed a new user's Mongo rules document, and never written back
    to."""
    with open(settings.RULES_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class RuleEngine:
    """Loads one user's rules from their Mongo document and decides which
    folder a file should land in. If the document doesn't exist yet, seeds
    it once from `seed` (defaults to the on-disk config/rules.json
    template)."""

    def __init__(self, database, doc_id: str, watch_root: Path, seed: dict | None = None):
        self.db = database
        self.doc_id = doc_id
        self.watch_root = watch_root
        self._seed = seed
        self.rules: dict = {}
        self.reload()

    def reload(self) -> None:
        with _lock:
            doc = self.db.rules.find_one({"_id": self.doc_id})
            if doc is None:
                template = self._seed if self._seed is not None else _load_default_template()
                doc = dict(template)
                doc["_id"] = self.doc_id
                self.db.rules.insert_one(doc)
            self.rules = {k: v for k, v in doc.items() if k != "_id"}

    def save(self, new_rules: dict) -> None:
        with _lock:
            self.rules = new_rules
            replacement = dict(new_rules)
            replacement["_id"] = self.doc_id
            self.db.rules.replace_one({"_id": self.doc_id}, replacement, upsert=True)

    def _validated(self, folder: str) -> str | None:
        if is_within_watch_folder(folder, self.watch_root):
            return folder
        logger.warning(
            "Ignoring rule destination outside the watch folder: %r", folder
        )
        return None

    def classify(self, filename: str, file_size_bytes: int) -> str:
        """Return the destination folder name for a given file."""
        name_lower = filename.lower()
        ext = Path(filename).suffix.lower()

        for rule in self.rules.get("keyword_rules", []):
            if rule["keyword"].lower() in name_lower:
                folder = self._validated(rule["folder"])
                if folder:
                    return folder

        extension_rules = self.rules.get("extension_rules", {})
        if ext in extension_rules:
            folder = self._validated(extension_rules[ext])
            if folder:
                return folder

        threshold_mb = self.rules.get("large_file_threshold_mb")
        if (
            self.rules.get("large_file_enabled", True)
            and threshold_mb
            and file_size_bytes > threshold_mb * 1024 * 1024
        ):
            folder = self._validated(self.rules.get("large_file_folder", "Large Files"))
            if folder:
                return folder

        for category, extensions in self.rules.get("categories", {}).items():
            if ext in extensions:
                return self._validated(category) or "Others"

        if ext and self.rules.get("auto_organize_unknown_extensions", True):
            auto_folder = f"{ext[1:].upper()} Files"
            folder = self._validated(auto_folder)
            if folder:
                return folder

        return self._validated(self.rules.get("default_category", "Others")) or "Others"

    def should_timestamp_rename(self, category: str) -> bool:
        if not self.rules.get("enable_timestamp_rename", False):
            return False
        return category in self.rules.get("timestamp_rename_categories", [])

    @property
    def archive_after_days(self) -> int:
        return self.rules.get("archive_after_days", 30)

    @property
    def archive_folder(self) -> str:
        return self.rules.get("archive_folder", "Archive")


def get_rule_engine(db, user_id: int, watch_root: Path) -> RuleEngine:
    """The single choke point for obtaining a user's rule engine -- every
    caller (routes, organizer, watcher, archive scheduler) goes through
    this rather than constructing RuleEngine directly, so the test-only
    override seam above works everywhere uniformly."""
    if _test_engine_override is not None:
        return _test_engine_override
    return RuleEngine(db, doc_id=str(user_id), watch_root=watch_root)
