import json
import logging
import threading
from pathlib import Path

from config.settings import settings
from rules.classifier import classify_file, classify_file_explained, is_within_watch_folder
from rules.classifier import should_timestamp_rename as _should_timestamp_rename

_lock = threading.Lock()
logger = logging.getLogger("fileflow.rules")

# Test-only seam: when set, get_rule_engine() returns this instance for
# every caller (routes, organizer, watcher, archive scheduler) instead of
# constructing a real per-user one -- lets tests freely mutate one shared
# `rules` dict via the `test_rules` fixture. Always None in production.
_test_engine_override: "RuleEngine | None" = None


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

    def classify(self, filename: str, file_size_bytes: int, file_path: Path | None = None) -> str:
        """Return the destination folder name for a given file."""
        return classify_file(self.rules, filename, file_size_bytes, self.watch_root, file_path)

    def classify_explained(
        self, filename: str, file_size_bytes: int, file_path: Path | None = None
    ) -> dict:
        """Same decision as classify() above, plus the explanation of which
        rule (if any) produced it -- see classify_file_explained()'s
        docstring, rules.classifier. Both methods evaluate the exact same
        rules dict; classify() is never re-derived independently."""
        return classify_file_explained(
            self.rules, filename, file_size_bytes, self.watch_root, file_path
        )

    def should_timestamp_rename(self, category: str) -> bool:
        return _should_timestamp_rename(self.rules, category)

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
