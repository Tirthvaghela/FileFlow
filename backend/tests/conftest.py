import uuid

import pytest
from fastapi.testclient import TestClient

import rules.rule_engine as rule_engine_module
from api.rate_limit import reset_all as reset_rate_limits
from config.settings import settings
from database.db import client as mongo_client, get_db, insert_with_id
from main import app
from models.models import Document, new_activity_log
from rules.rule_engine import RuleEngine

BASE_RULES = {
    "categories": {
        "Documents": [".pdf", ".txt"],
        "Images": [".jpg", ".png"],
    },
    "extension_rules": {".py": "Python Projects"},
    "keyword_rules": [
        {"keyword": "invoice", "folder": "Finance Folder"},
    ],
    "large_file_threshold_mb": 1,
    "large_file_folder": "Large Files",
    "archive_after_days": 30,
    "archive_folder": "Archive",
    "default_category": "Others",
    "enable_timestamp_rename": False,
    "timestamp_rename_categories": [],
}


@pytest.fixture(autouse=True)
def _disable_real_uipath(monkeypatch):
    """Tests must stay hermetic regardless of what a developer's local .env
    has set for the live app -- never shell out to a real UiPath Robot.
    test_uipath_service.py overrides this explicitly per-test where it
    needs to exercise the real flag."""
    monkeypatch.setattr(settings, "UIPATH_ENABLED", False)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """The login/register limiters are process-global state (keyed by
    caller IP), so without a reset every test would share one bucket with
    every other test in the run -- reset before each test regardless of
    execution order."""
    reset_rate_limits()


@pytest.fixture()
def db_session():
    """A disposable, isolated Mongo database per test, dropped in teardown.
    Uses the real local mongod (already required to run the app itself)
    rather than an in-memory substitute -- there's no in-memory Mongo
    equivalent to SQLite's ':memory:' without extra tooling, and one isn't
    needed since mongod is already running locally."""
    db_name = f"fileflow_test_{uuid.uuid4().hex}"
    database = mongo_client[db_name]
    try:
        yield database
    finally:
        mongo_client.drop_database(db_name)


@pytest.fixture()
def watch_folder(tmp_path, monkeypatch):
    folder = tmp_path / "watch"
    folder.mkdir()
    monkeypatch.setattr(settings, "WATCH_FOLDER", folder)
    # keep the stability-poll loop fast in tests; it isn't under test itself
    monkeypatch.setattr(settings, "STABILITY_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(settings, "STABILITY_TIMEOUT", 1.0)
    return folder


@pytest.fixture()
def test_user(watch_folder):
    """A fake "current user" dict, the same shape production code reads
    (user["id"], user["watch_folder"]) -- for tests that call organizer.py
    functions directly rather than going through the authenticated client."""
    return {"id": 1, "email": "test@example.com", "watch_folder": str(watch_folder)}


@pytest.fixture()
def test_rules(db_session, watch_folder, monkeypatch):
    """A rules dict every caller (routes, organizer, watcher, archive
    scheduler) transparently shares for the duration of the test, via
    rule_engine.get_rule_engine()'s test-only override seam -- freely
    mutable, e.g. test_rules["large_file_enabled"] = False."""
    rules = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in BASE_RULES.items()}
    engine = RuleEngine(db_session, doc_id="test-rules", watch_root=watch_folder, seed=rules)
    monkeypatch.setattr(rule_engine_module, "_test_engine_override", engine)
    return engine.rules


@pytest.fixture()
def test_engine(test_rules):
    """The RuleEngine instance backing `test_rules` -- for call sites that
    take a real engine object rather than its .rules dict directly, e.g.
    build_final_name()/resolve_destination()."""
    return rule_engine_module._test_engine_override


@pytest.fixture()
def anon_client(db_session, watch_folder, test_rules):
    """A TestClient with no session -- for exercising unauthenticated and
    failure paths. (The `client` fixture in test_routes.py auto-registers,
    which is exactly what these tests must NOT start from.)"""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def log_factory(db_session):
    """Persists an activity log document with sensible defaults, overridable
    per call -- e.g. log_factory(action="duplicate_skipped", timestamp=some_datetime)."""

    def _make(**overrides):
        defaults = dict(
            user_id=1,
            original_filename="a.txt",
            final_filename="a.txt",
            source_path="C:/watch/a.txt",
            destination_path="C:/watch/Documents/a.txt",
            category="Documents",
            action="moved",
            file_size=100,
            file_hash="deadbeef",
        )
        defaults.update(overrides)
        doc = insert_with_id(db_session, "activity_log", new_activity_log(**defaults))
        return Document(doc)

    return _make
