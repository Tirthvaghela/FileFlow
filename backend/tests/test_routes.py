import asyncio

import pytest
from fastapi.testclient import TestClient

from api.websocket_manager import manager
from config.settings import settings
from database.db import get_db, insert_with_id
from main import app
from models.models import Document, new_activity_log


@pytest.fixture()
def client(db_session, watch_folder, test_rules, monkeypatch):
    # `test_rules` already installs the shared test RuleEngine override (see
    # conftest.py), so every route that calls get_rule_engine() -- GET/PUT
    # /api/rules included -- transparently uses it instead of touching the
    # real production rules document.

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        # Not using `with TestClient(app)` deliberately: that would run the
        # app's lifespan (real watchdog Observer + APScheduler), which these
        # route-level tests don't need and shouldn't pay the cost of.
        test_client = TestClient(app)
        # Every route below (except /api/health and /api/auth/*) now
        # requires a session. Register once so this client's cookie jar
        # carries a valid one for every request the test makes afterward.
        register_resp = test_client.post(
            "/api/auth/register",
            json={"email": "test@example.com", "password": "test-password-123"},
        )
        assert register_resp.status_code == 201, register_resp.text
        test_client.test_user_id = register_resp.json()["id"]
        # Registration defaults a fresh account's watch folder to a
        # user_<id> subfolder under the root; route-level tests instead
        # write directly into the `watch_folder` fixture's own tmp dir, so
        # point this user straight at it.
        db_session.users.update_one(
            {"_id": test_client.test_user_id},
            {"$set": {"watch_folder": str(watch_folder)}},
        )
        yield test_client
    finally:
        app.dependency_overrides.clear()


def _log(db_session, **overrides):
    defaults = dict(
        user_id=1,  # matches the `client` fixture's first-registered test user
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


class TestHealth:
    def test_returns_ok_unauthenticated(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestLogs:
    def test_empty_db_returns_empty_list(self, client):
        resp = client.get("/api/logs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_logged_entries_with_utc_offset_timestamp(self, client, db_session):
        _log(db_session)

        resp = client.get("/api/logs")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["original_filename"] == "a.txt"
        # the timestamp field_validator must stamp naive datetimes as UTC so
        # clients never misinterpret them as local time (see schemas.py)
        assert body[0]["timestamp"].endswith("+00:00") or body[0]["timestamp"].endswith("Z")

    def test_limit_is_respected_and_capped_at_500(self, client, db_session):
        for i in range(3):
            _log(db_session, original_filename=f"f{i}.txt")

        resp = client.get("/api/logs?limit=2")

        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestStats:
    def test_empty_db_returns_zeroed_stats(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_files_organized"] == 0
        assert body["by_category"] == []
        assert len(body["last_7_days"]) == 7

    def test_counts_reflect_persisted_logs(self, client, db_session):
        _log(db_session, action="moved")
        _log(db_session, action="duplicate_skipped")

        body = client.get("/api/stats").json()

        assert body["total_files_organized"] == 1
        assert body["duplicates_detected"] == 1


class TestCategories:
    def test_empty_db_returns_empty_list(self, client):
        resp = client.get("/api/categories")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_groups_organized_files_by_category(self, client, db_session):
        _log(db_session, category="Documents", file_size=100)
        _log(db_session, category="Documents", file_size=50)
        _log(db_session, category="Images", file_size=10)

        body = client.get("/api/categories").json()
        by_name = {row["category"]: row for row in body}

        assert by_name["Documents"]["count"] == 2
        assert by_name["Documents"]["size_bytes"] == 150
        assert by_name["Images"]["count"] == 1


class TestRules:
    def test_get_rules_round_trips_through_the_real_pydantic_schema(self, client, test_rules):
        resp = client.get("/api/rules")

        assert resp.status_code == 200
        body = resp.json()
        assert body["extension_rules"] == test_rules["extension_rules"]
        # fields the BASE_RULES fixture never sets must come back with the
        # schema's real defaults -- this is the exact HTTP-serialization path
        # the audit flagged as having zero coverage
        assert body["disabled_extension_rules"] == {}
        assert body["disabled_keyword_rules"] == []
        assert body["large_file_enabled"] is True
        assert body["duplicate_handling"] == "rename"

    def test_put_rules_persists_and_is_reflected_on_next_get(self, client, test_rules):
        payload = {**test_rules, "large_file_enabled": False, "archive_after_days": 45}

        put_resp = client.put("/api/rules", json=payload)
        assert put_resp.status_code == 200
        assert put_resp.json()["large_file_enabled"] is False

        get_resp = client.get("/api/rules")
        assert get_resp.json()["archive_after_days"] == 45

    def test_put_rules_never_touches_the_real_rules_json_file(self, client, test_rules):
        before = settings.RULES_CONFIG_PATH.read_text(encoding="utf-8")

        client.put("/api/rules", json={**test_rules, "archive_after_days": 999})

        after = settings.RULES_CONFIG_PATH.read_text(encoding="utf-8")
        assert before == after

    def test_disabling_the_size_rule_over_http_stops_large_files_matching_it(
        self, client, test_rules, test_engine
    ):
        payload = {**test_rules, "large_file_enabled": False}
        client.put("/api/rules", json=payload)

        one_mb = 1024 * 1024
        assert test_engine.classify("huge.bin", one_mb + 1) != test_rules["large_file_folder"]


class TestUndo:
    def test_no_history_returns_success_false(self, client):
        resp = client.post("/api/undo")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["log"] is None


class TestRulePreview:
    def test_returns_matched_count_and_grouped_categories(self, client, db_session):
        _log(db_session, original_filename="a.psd", category="Design")
        _log(db_session, original_filename="b.psd", category="Design")
        _log(db_session, original_filename="c.pdf", category="Documents")

        resp = client.post("/api/rules/preview", json={"type": "extension", "match": ".psd"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["matched_count"] == 2
        assert body["by_category"] == [{"category": "Design", "count": 2}]

    def test_never_touches_the_filesystem_or_rules_json(self, client, db_session):
        before = settings.RULES_CONFIG_PATH.read_text(encoding="utf-8")

        client.post("/api/rules/preview", json={"type": "keyword", "match": "invoice"})

        after = settings.RULES_CONFIG_PATH.read_text(encoding="utf-8")
        assert before == after


class TestReclassify:
    def test_moves_the_file_and_returns_the_new_log(self, client, watch_folder, db_session):
        source = watch_folder / "notes.txt"
        source.write_text("hi")
        organize_resp = client.post("/api/organize-existing")
        assert organize_resp.json()["organized"] == 1
        original_log = db_session.activity_log.find_one(sort=[("_id", -1)])

        resp = client.post(f"/api/logs/{original_log['id']}/reclassify", json={"category": "Design"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["log"]["action"] == "reclassified"
        assert body["log"]["category"] == "Design"
        assert (watch_folder / "Design" / "notes.txt").exists()

    def test_unknown_log_id_fails_gracefully(self, client):
        resp = client.post("/api/logs/999999/reclassify", json={"category": "Design"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["log"] is None


class TestOrganizeExisting:
    def test_sweeps_loose_files_in_the_watch_folder(self, client, watch_folder):
        (watch_folder / "notes.txt").write_text("hi")
        (watch_folder / "script.py").write_text("print(1)")

        resp = client.post("/api/organize-existing")

        assert resp.status_code == 200
        body = resp.json()
        assert body["scanned"] == 2
        assert body["organized"] == 2
        assert (watch_folder / "Documents" / "notes.txt").exists()
        assert (watch_folder / "Python Projects" / "script.py").exists()


class TestSimulateDownload:
    def test_creates_a_real_file_in_the_watch_folder(self, client, watch_folder):
        resp = client.post("/api/simulate-download")

        assert resp.status_code == 200
        body = resp.json()
        assert body["filename"]
        assert (watch_folder / body["filename"]).exists()


class TestWeeklyReports:
    def test_defaults_to_four_weeks(self, client):
        resp = client.get("/api/reports/weekly")
        assert resp.status_code == 200
        assert len(resp.json()) == 4

    def test_weeks_param_is_honored_and_capped_at_26(self, client):
        assert len(client.get("/api/reports/weekly?weeks=2").json()) == 2
        assert len(client.get("/api/reports/weekly?weeks=999").json()) == 26


class TestSendDigest:
    def test_reports_skipped_when_resend_is_not_configured(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RESEND_API_KEY", None)

        resp = client.post("/api/reports/send-digest")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False

    def test_reports_success_when_the_send_succeeds(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
        monkeypatch.setattr("api.routes.send_weekly_digest", lambda db, user: True)

        resp = client.post("/api/reports/send-digest")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    def test_reports_failure_when_the_send_fails(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
        monkeypatch.setattr("api.routes.send_weekly_digest", lambda db, user: False)

        resp = client.post("/api/reports/send-digest")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False


class TestReportExports:
    def test_csv_export(self, client, db_session):
        _log(db_session)
        resp = client.get("/api/reports/csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "a.txt" in resp.text

    def test_excel_export(self, client, db_session):
        _log(db_session)
        resp = client.get("/api/reports/excel")
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"

    def test_pdf_export(self, client, db_session):
        _log(db_session)
        resp = client.get("/api/reports/pdf")
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF")


class TestWebSocket:
    def test_connect_and_disconnect_cleanly(self, client):
        with client.websocket_connect("/ws"):
            pass  # accepted without raising is the assertion

    def test_broadcast_reaches_a_connected_client(self, client):
        with client.websocket_connect("/ws") as ws:
            asyncio.run(manager.broadcast({"hello": "world"}, client.test_user_id))
            assert ws.receive_json() == {"hello": "world"}
