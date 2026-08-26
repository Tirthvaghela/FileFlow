import asyncio

import pytest
from fastapi.testclient import TestClient

from api.websocket_manager import manager
from config.settings import settings
from database.db import get_db, insert_with_id
from main import app
from models.models import Document, new_activity_log
from services.digest_service import DigestOutcome


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
    def test_empty_watch_folder_returns_empty_list(self, client):
        resp = client.get("/api/categories")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_groups_files_currently_on_disk_by_category(self, client, watch_folder):
        (watch_folder / "Documents").mkdir()
        (watch_folder / "Documents" / "a.pdf").write_text("a" * 100)
        (watch_folder / "Documents" / "b.pdf").write_text("a" * 50)
        (watch_folder / "Images").mkdir()
        (watch_folder / "Images" / "c.png").write_text("a" * 10)

        body = client.get("/api/categories").json()
        by_name = {row["category"]: row for row in body}

        assert by_name["Documents"]["count"] == 2
        assert by_name["Documents"]["size_bytes"] == 150
        assert by_name["Images"]["count"] == 1

    def test_a_category_disappears_once_its_last_file_is_gone(
        self, client, watch_folder, db_session
    ):
        # A file that was organized into a category, then later deleted
        # (or reclassified/archived away), must not leave that category
        # lingering in the overview forever -- this is a live disk read,
        # not a historical activity_log aggregate, precisely so a deleted
        # file's old category stops appearing once nothing is left in it.
        (watch_folder / "Documents").mkdir()
        old = watch_folder / "Documents" / "old.pdf"
        old.write_text("bye")
        _log(db_session, category="Documents", destination_path=str(old))
        assert client.get("/api/categories").json()[0]["category"] == "Documents"

        client.request(
            "DELETE", "/api/categories/Documents/files", json={"path": str(old)}
        )

        assert client.get("/api/categories").json() == []

    def test_excludes_the_configured_archive_folder(self, client, watch_folder, test_rules):
        test_rules["archive_folder"] = "Archive"
        (watch_folder / "Archive").mkdir()
        (watch_folder / "Archive" / "old.pdf").write_text("hi")

        assert client.get("/api/categories").json() == []


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

    def test_put_rules_rejects_an_uncompilable_regex_pattern(self, client, test_rules):
        payload = {**test_rules, "regex_rules": [{"pattern": "[unclosed", "folder": "Camera"}]}

        resp = client.put("/api/rules", json=payload)

        assert resp.status_code == 422

    def test_put_rules_accepts_a_valid_regex_pattern(self, client, test_rules):
        payload = {**test_rules, "regex_rules": [{"pattern": r"^IMG_\d+", "folder": "Camera"}]}

        resp = client.put("/api/rules", json=payload)

        assert resp.status_code == 200
        assert resp.json()["regex_rules"] == [{"pattern": r"^IMG_\d+", "folder": "Camera"}]

    def test_put_rules_rejects_a_negative_date_rule_threshold(self, client, test_rules):
        payload = {**test_rules, "date_rules": [{"older_than_days": -5, "folder": "Old Stuff"}]}

        resp = client.put("/api/rules", json=payload)

        assert resp.status_code == 422

    def test_put_rules_rejects_a_negative_large_file_threshold(self, client, test_rules):
        # Unlike DateRule.older_than_days (Field(ge=0)), large_file_threshold_mb
        # had no lower-bound constraint at all -- a negative value makes
        # classify_file()'s "file_size_bytes > threshold_mb * 1024 * 1024"
        # check true for every file regardless of size (any real file size
        # is > a negative number), silently routing everything into the
        # large-file folder. The real Settings UI's slider is bounded to
        # [10, 2000] so this was never reachable there, but nothing stopped
        # a direct API call from saving it.
        payload = {**test_rules, "large_file_threshold_mb": -1}

        resp = client.put("/api/rules", json=payload)

        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "pattern",
        [
            pytest.param(r"(a+)+$", id="nested-quantifier"),
            pytest.param(r"(a|aa)+$", id="overlapping-alternation"),
            pytest.param(r"^(a|a?)+$", id="nested-optional"),
        ],
    )
    def test_put_rules_rejects_a_catastrophic_backtracking_pattern(self, client, test_rules, pattern):
        # Confirmed live (standalone reproduction, not part of this suite):
        # each of these compiles fine -- re.compile() alone already accepted
        # them -- but re.search() against a filename with as few as 25
        # repeated characters already took multiple seconds, growing
        # exponentially from there. classify_file() calls re.search() on
        # every regex_rules entry for every file organized, so a pattern
        # like this reaching persistence is a real ReDoS risk against real
        # filenames, well within Windows' normal filename length limits.
        payload = {**test_rules, "regex_rules": [{"pattern": pattern, "folder": "Camera"}]}

        resp = client.put("/api/rules", json=payload)

        assert resp.status_code == 422
        assert "backtracking" in resp.text.lower()

    def test_put_rules_still_accepts_an_ordinary_alternation_pattern(self, client, test_rules):
        # Non-regression: alternatives that don't overlap (no branch is a
        # prefix of another) must not be caught by the backtracking-shape
        # heuristic just because the group is quantified.
        payload = {
            **test_rules,
            "regex_rules": [{"pattern": r"(Invoice|Receipt)+", "folder": "Finance"}],
        }

        resp = client.put("/api/rules", json=payload)

        assert resp.status_code == 200

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


class TestUndoSpecificLog:
    def test_undoes_a_specific_row_by_id(self, client, watch_folder, db_session):
        source = watch_folder / "notes.txt"
        source.write_text("hi")
        client.post("/api/organize-existing")
        log = db_session.activity_log.find_one(sort=[("_id", -1)])

        resp = client.post(f"/api/logs/{log['id']}/undo")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert source.exists()
        assert not (watch_folder / log["category"] / "notes.txt").exists()

    def test_unknown_log_id_fails_gracefully(self, client):
        resp = client.post("/api/logs/999999/undo")

        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_can_undo_an_older_row_without_touching_a_newer_one(
        self, client, watch_folder, db_session
    ):
        # Two independently organized files -- undoing the FIRST one
        # specifically must leave the second alone, unlike the LIFO-only
        # /api/undo endpoint which can only ever reach the most recent row.
        first = watch_folder / "first.txt"
        first.write_text("1")
        client.post("/api/organize-existing")
        first_log = db_session.activity_log.find_one(sort=[("_id", -1)])

        second = watch_folder / "second.txt"
        second.write_text("2")
        client.post("/api/organize-existing")
        second_log = db_session.activity_log.find_one(sort=[("_id", -1)])

        resp = client.post(f"/api/logs/{first_log['id']}/undo")

        assert resp.json()["success"] is True
        assert first.exists()
        assert (watch_folder / second_log["category"] / "second.txt").exists()

    def test_cannot_undo_the_same_row_twice(self, client, watch_folder, db_session):
        source = watch_folder / "notes.txt"
        source.write_text("hi")
        client.post("/api/organize-existing")
        log = db_session.activity_log.find_one(sort=[("_id", -1)])

        client.post(f"/api/logs/{log['id']}/undo")
        resp = client.post(f"/api/logs/{log['id']}/undo")

        assert resp.json()["success"] is False


class TestCategoryFiles:
    def test_lists_files_in_a_category_folder(self, client, watch_folder):
        (watch_folder / "Documents").mkdir()
        (watch_folder / "Documents" / "a.pdf").write_text("aaaa")
        (watch_folder / "Documents" / "b.pdf").write_text("b")

        resp = client.get("/api/categories/Documents/files")

        assert resp.status_code == 200
        names = {f["name"] for f in resp.json()}
        assert names == {"a.pdf", "b.pdf"}

    def test_sorted_largest_first_by_default(self, client, watch_folder):
        (watch_folder / "Documents").mkdir()
        (watch_folder / "Documents" / "small.pdf").write_text("a")
        (watch_folder / "Documents" / "big.pdf").write_text("a" * 100)

        resp = client.get("/api/categories/Documents/files")

        names = [f["name"] for f in resp.json()]
        assert names == ["big.pdf", "small.pdf"]

    def test_empty_or_missing_category_returns_empty_list(self, client):
        resp = client.get("/api/categories/NoSuchCategory/files")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_deletes_a_file_and_logs_it(self, client, watch_folder, db_session):
        (watch_folder / "Documents").mkdir()
        target = watch_folder / "Documents" / "old.pdf"
        target.write_text("bye")

        resp = client.request(
            "DELETE", "/api/categories/Documents/files", json={"path": str(target)}
        )

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert not target.exists()
        log = db_session.activity_log.find_one(sort=[("_id", -1)])
        assert log["action"] == "deleted"
        assert log["category"] == "Documents"

    def test_rejects_a_path_outside_any_watched_category_folder(self, client, tmp_path):
        outside = tmp_path / "outside" / "evil.txt"
        outside.parent.mkdir()
        outside.write_text("do not delete me")

        resp = client.request(
            "DELETE", "/api/categories/Documents/files", json={"path": str(outside)}
        )

        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert outside.exists()

    def test_rejects_a_path_traversal_attempt(self, client, watch_folder):
        (watch_folder / "Documents").mkdir()
        real_file_elsewhere = watch_folder / "secret.txt"
        real_file_elsewhere.write_text("do not delete me")
        traversal_path = str(watch_folder / "Documents" / ".." / "secret.txt")

        resp = client.request(
            "DELETE", "/api/categories/Documents/files", json={"path": traversal_path}
        )

        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert real_file_elsewhere.exists()


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


class TestRuleSimulate:
    def test_reports_no_changes_for_an_identical_rule_set(self, client, test_rules, db_session):
        _log(db_session, original_filename="a.pdf", category="Documents")

        resp = client.post("/api/rules/simulate", json=test_rules)

        assert resp.status_code == 200
        body = resp.json()
        assert body["compared_count"] == 1
        assert body["unchanged_count"] == 1
        assert body["changes"] == []

    def test_reports_a_file_that_would_now_be_classified_differently(
        self, client, test_rules, db_session
    ):
        _log(db_session, original_filename="report.psd", final_filename="report.psd", category="Others")
        candidate = {**test_rules, "extension_rules": {**test_rules["extension_rules"], ".psd": "Design"}}

        resp = client.post("/api/rules/simulate", json=candidate)

        assert resp.status_code == 200
        body = resp.json()
        assert body["compared_count"] == 1
        assert body["unchanged_count"] == 0
        assert body["changes"] == [
            {
                "filename": "report.psd",
                "file_size_bytes": 100,
                "previous_category": "Others",
                "new_category": "Design",
            }
        ]

    def test_never_saves_the_candidate_rules(self, client, test_rules, db_session):
        candidate = {**test_rules, "extension_rules": {**test_rules["extension_rules"], ".psd": "Design"}}

        client.post("/api/rules/simulate", json=candidate)

        get_resp = client.get("/api/rules")
        assert ".psd" not in get_resp.json()["extension_rules"]

    def test_excludes_deleted_rows_from_the_comparison(self, client, test_rules, db_session):
        _log(db_session, action="deleted", original_filename="gone.pdf", category="Documents")

        resp = client.post("/api/rules/simulate", json=test_rules)

        assert resp.json()["compared_count"] == 0


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

    def test_sweeps_additional_watch_folders_too(self, client, watch_folder, tmp_path):
        extra = tmp_path / "extra_watch_folder"
        add_resp = client.post("/api/settings/watch-folders", json={"path": str(extra)})
        assert add_resp.status_code == 200

        (watch_folder / "notes.txt").write_text("hi")
        (extra / "script.py").write_text("print(1)")

        resp = client.post("/api/organize-existing")

        assert resp.status_code == 200
        body = resp.json()
        assert body["scanned"] == 2
        assert body["organized"] == 2
        # Each file lands relative to its OWN folder, not the primary --
        # script.py must not end up nested under the primary watch_folder.
        assert (watch_folder / "Documents" / "notes.txt").exists()
        assert (extra / "Python Projects" / "script.py").exists()


class TestSimulateDownload:
    def test_serves_a_real_downloadable_file(self, client, watch_folder):
        resp = client.get("/api/simulate-download")

        assert resp.status_code == 200
        assert resp.content
        disposition = resp.headers["content-disposition"]
        assert disposition.startswith("attachment; filename=FileFlow_Demo_")
        # The whole point is that the backend no longer writes into the
        # watch folder itself -- the browser's own download is what lands
        # there for the already-running watcher to pick up. (Registration
        # already creates the user's own watch subfolder, so check for
        # files, not just an empty directory.)
        assert [p for p in watch_folder.rglob("*") if p.is_file()] == []


class TestWeeklyReports:
    def test_defaults_to_four_weeks(self, client):
        resp = client.get("/api/reports/weekly")
        assert resp.status_code == 200
        assert len(resp.json()) == 4

    def test_weeks_param_is_honored_and_capped_at_26(self, client):
        assert len(client.get("/api/reports/weekly?weeks=2").json()) == 2
        assert len(client.get("/api/reports/weekly?weeks=999").json()) == 26


class TestSendDigest:
    def test_reports_skipped_when_smtp_is_not_configured(self, client, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_USERNAME", None)
        monkeypatch.setattr(settings, "SMTP_PASSWORD", None)

        resp = client.post("/api/reports/send-digest")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "not configured" in body["message"].lower()

    def test_reports_success_when_the_send_succeeds(self, client, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_USERNAME", "someone@gmail.com")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "app-password")
        monkeypatch.setattr("api.routes.send_weekly_digest", lambda db, user: DigestOutcome.SENT)

        resp = client.post("/api/reports/send-digest")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    def test_reports_failure_when_the_send_fails(self, client, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_USERNAME", "someone@gmail.com")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "app-password")
        monkeypatch.setattr("api.routes.send_weekly_digest", lambda db, user: DigestOutcome.FAILED)

        resp = client.post("/api/reports/send-digest")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "check server logs" in body["message"].lower()

    def test_distinguishes_no_activity_from_an_actual_failure(self, client, monkeypatch):
        """Regression test for the observability gap this task fixes: both
        "nothing to report" and "the send itself failed" used to collapse
        into the exact same generic "Failed to send the digest -- check
        server logs" message -- misleading for the (very common) case
        where nothing was actually wrong, there was just no activity."""
        monkeypatch.setattr(settings, "SMTP_USERNAME", "someone@gmail.com")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "app-password")
        monkeypatch.setattr(
            "api.routes.send_weekly_digest", lambda db, user: DigestOutcome.SKIPPED_NO_ACTIVITY
        )

        resp = client.post("/api/reports/send-digest")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "no activity" in body["message"].lower()
        assert "check server logs" not in body["message"].lower(), (
            "a zero-activity skip must not be worded like an actual failure"
        )


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


class TestOnboardingTemplates:
    def test_lists_all_four_starter_templates(self, client):
        resp = client.get("/api/onboarding/templates")

        assert resp.status_code == 200
        ids = {t["id"] for t in resp.json()}
        assert ids == {"general", "student", "developer", "photographer"}

    def test_applying_a_template_overwrites_the_users_rules(self, client):
        resp = client.post("/api/onboarding/templates/developer/apply")

        assert resp.status_code == 200
        body = resp.json()
        assert body["extension_rules"][".py"] == "Python Projects"
        assert body["extension_rules"][".ipynb"] == "Notebooks"

        get_resp = client.get("/api/rules")
        assert get_resp.json()["extension_rules"][".sql"] == "SQL Scripts"

    def test_unknown_template_id_404s(self, client):
        resp = client.post("/api/onboarding/templates/not-a-real-template/apply")
        assert resp.status_code == 404


class TestWebSocket:
    def test_connect_and_disconnect_cleanly(self, client):
        with client.websocket_connect("/ws"):
            pass  # accepted without raising is the assertion

    def test_broadcast_reaches_a_connected_client(self, client):
        with client.websocket_connect("/ws") as ws:
            asyncio.run(manager.broadcast({"hello": "world"}, client.test_user_id))
            assert ws.receive_json() == {"hello": "world"}
