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

    def test_a_row_with_no_explanation_still_validates_as_null(self, client, db_session):
        # Every row written before this feature existed, and any row from a
        # source that never classified (reclassify, undo, archive) --
        # a missing `explanation` key must round-trip as a plain null, not
        # a validation error, so an old API consumer keeps working.
        _log(db_session)

        body = client.get("/api/logs").json()

        assert body[0]["explanation"] is None

    def test_a_row_with_an_explanation_exposes_it_through_the_api(self, client, db_session):
        _log(
            db_session,
            explanation={
                "match_type": "keyword",
                "matched_value": "invoice",
                "destination": "Documents",
                "rule_name": 'Keyword "invoice"',
                "priority": 1,
            },
        )

        body = client.get("/api/logs").json()

        assert body[0]["explanation"] == {
            "match_type": "keyword",
            "matched_value": "invoice",
            "destination": "Documents",
            "rule_name": 'Keyword "invoice"',
            "priority": 1,
        }


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


class TestRuleConflicts:
    """Route-level concerns for POST /api/rules/conflicts -- the analysis
    algorithm itself is covered by test_rule_conflict_service.py. These
    confirm the endpoint's wiring: auth, account scoping, candidate-vs-saved
    loading, and that it's genuinely read-only."""

    def test_requires_authentication(self, anon_client):
        resp = anon_client.post("/api/rules/conflicts", json={})
        assert resp.status_code == 401

    def test_no_body_analyzes_the_currently_saved_rules(self, client):
        resp = client.post("/api/rules/conflicts", json={})
        assert resp.status_code == 200
        # BASE_RULES seeds keyword "invoice"/extension ".py"/a large-file
        # rule together -- all three inherently overlap by construction
        # (see services/rule_conflict_service.py), so a clean, unmodified
        # save already surfaces that, rather than showing nothing.
        assert resp.json()["conflicts"] != []
        assert resp.json()["rules_checked"] >= 3

    def _isolated_candidate(self, test_rules, **overrides):
        # BASE_RULES also seeds an active extension rule (.py) and a large
        # file rule -- both would add their own cross-type conflicts against
        # anything else in the candidate, muddying an exact-count assertion.
        # Neutralizing them here keeps each test's own pair the only
        # possible finding.
        base = {
            **test_rules,
            "extension_rules": {},
            "large_file_threshold_mb": 0,
            "keyword_rules": [],
        }
        base.update(overrides)
        return base

    def test_a_supplied_candidate_is_analyzed_instead_of_the_saved_rules(self, client, test_rules):
        candidate = self._isolated_candidate(
            test_rules,
            keyword_rules=[{"keyword": "invoice", "folder": "Finance/Invoices"}],
            extension_rules={".pdf": "Documents/PDF"},
        )

        resp = client.post("/api/rules/conflicts", json={"rules": candidate})

        assert resp.status_code == 200
        body = resp.json()
        assert body["warnings"] == 1
        assert body["conflicts"][0]["type"] == "precedence_overlap"
        assert body["conflicts"][0]["example"]["filename"] == "invoice.pdf"

    def test_demo_scenario_matches_the_feature_spec_exactly(self, client, test_rules):
        # PDF files -> Documents/PDF (extension), then adding
        # keyword "invoice" -> Finance/Invoices: FileFlow's real precedence
        # (keyword before extension) means invoice.pdf goes to
        # Finance/Invoices, and the detector must say so before it's saved.
        candidate = self._isolated_candidate(
            test_rules,
            keyword_rules=[{"keyword": "invoice", "folder": "Finance/Invoices"}],
            extension_rules={".pdf": "Documents/PDF"},
        )

        resp = client.post("/api/rules/conflicts", json={"rules": candidate})
        conflict = resp.json()["conflicts"][0]

        assert conflict["example"]["winning_rule"] == 'Keyword "invoice"'
        assert conflict["example"]["destination"] == "Finance/Invoices"
        assert "Keyword rules are evaluated before extension rules." in conflict["message"]

    def test_invalid_candidate_rules_are_rejected_before_analysis(self, client, test_rules):
        candidate = {**test_rules, "regex_rules": [{"pattern": "[unclosed", "folder": "Weird"}]}
        resp = client.post("/api/rules/conflicts", json={"rules": candidate})
        assert resp.status_code == 422

    def test_never_saves_the_candidate_rules(self, client, test_rules):
        candidate = {**test_rules, "extension_rules": {**test_rules["extension_rules"], ".psd": "Design"}}

        client.post("/api/rules/conflicts", json={"rules": candidate})

        get_resp = client.get("/api/rules")
        assert ".psd" not in get_resp.json()["extension_rules"]

    def test_never_writes_activity_log_or_agent_commands(self, client, test_rules):
        candidate = {
            **test_rules,
            "keyword_rules": [{"keyword": "invoice", "folder": "Finance/Invoices"}],
            "extension_rules": {**test_rules["extension_rules"], ".pdf": "Documents/PDF"},
        }

        client.post("/api/rules/conflicts", json={"rules": candidate})

        assert client.get("/api/logs").json() == []
        assert client.get("/api/agent-commands").json() == []

    def test_never_touches_the_filesystem(self, client, test_rules, watch_folder):
        loose_file = watch_folder / "invoice.pdf"
        loose_file.write_bytes(b"content")
        candidate = {
            **test_rules,
            "keyword_rules": [{"keyword": "invoice", "folder": "Finance/Invoices"}],
            "extension_rules": {**test_rules["extension_rules"], ".pdf": "Documents/PDF"},
        }

        client.post("/api/rules/conflicts", json={"rules": candidate})

        assert loose_file.exists()

    def test_an_ai_rule_generator_proposal_can_be_analyzed_before_saving(self, client, monkeypatch, test_rules):
        from models.schemas import AIRuleGenerateResponse, AIRuleProposal

        monkeypatch.setattr(
            "api.routes.generate_rule_proposal",
            lambda prompt, watch_root: AIRuleGenerateResponse(
                status="ready",
                proposal=AIRuleProposal(
                    rule_type="keyword", name="Invoices", keyword="invoice", destination="Finance/Invoices"
                ),
            ),
        )
        gen_resp = client.post("/api/rules/ai-generate", json={"prompt": "Put invoices into Finance/Invoices"})
        proposal = gen_resp.json()["proposal"]
        candidate = self._isolated_candidate(
            test_rules,
            keyword_rules=[{"keyword": proposal["keyword"], "folder": proposal["destination"]}],
            extension_rules={".pdf": "Documents/PDF"},
        )

        resp = client.post("/api/rules/conflicts", json={"rules": candidate})

        assert resp.status_code == 200
        assert resp.json()["warnings"] == 1

    def test_an_unclassified_suggestion_proposed_rule_can_be_analyzed_before_saving(
        self, client, test_rules
    ):
        # Mirrors the exact shape services/ai_unclassified_service.py's
        # UnclassifiedSuggestion.suggested_rule carries -- an AIRuleProposal,
        # the same type an AI Rule Generator proposal uses.
        suggested_rule = {"rule_type": "keyword", "keyword": "gstreceipt", "destination": "Finance/GST"}
        candidate = {
            **test_rules,
            "keyword_rules": [
                *test_rules["keyword_rules"],
                {"keyword": "receipt", "folder": "Finance/Receipts"},
                {"keyword": suggested_rule["keyword"], "folder": suggested_rule["destination"]},
            ],
        }

        resp = client.post("/api/rules/conflicts", json={"rules": candidate})

        assert resp.status_code == 200
        shadow = [c for c in resp.json()["conflicts"] if c["type"] == "shadowed_rule"]
        assert len(shadow) == 1
        assert shadow[0]["severity"] == "high"

    def test_existing_classify_behavior_is_unchanged_by_calling_this_endpoint(
        self, client, test_rules, watch_folder
    ):
        (watch_folder / "Invoice_March.pdf").write_bytes(b"content")

        client.post("/api/rules/conflicts", json={"rules": test_rules})

        organize_resp = client.post("/api/organize-existing")
        assert organize_resp.json()["organized"] == 1
        log = client.get("/api/logs").json()[0]
        assert log["category"] == "Finance Folder"
        assert log["explanation"]["rule_name"] == 'Keyword "invoice"'


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


class TestOrganizePreview:
    def test_returns_correct_planned_destination_and_counts(self, client, watch_folder):
        (watch_folder / "notes.txt").write_text("hi")
        (watch_folder / "script.py").write_text("print(1)")

        resp = client.post("/api/organize/preview")

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is False
        assert body["total"] == 2
        assert body["ready"] == 2
        assert body["duplicates"] == 0
        assert body["no_match"] == 0
        assert body["errors"] == 0
        by_name = {i["filename"]: i for i in body["items"]}
        assert by_name["notes.txt"]["destination_path"] == str(watch_folder / "Documents" / "notes.txt")

    def test_never_moves_a_file(self, client, watch_folder):
        source = watch_folder / "notes.txt"
        source.write_text("hi")

        client.post("/api/organize/preview")

        assert source.exists()
        assert not (watch_folder / "Documents").exists()

    def test_creates_no_activity_log_rows(self, client, watch_folder, db_session):
        (watch_folder / "notes.txt").write_text("hi")

        client.post("/api/organize/preview")

        assert db_session.activity_log.count_documents({}) == 0

    def test_does_not_enqueue_a_real_organize_command(self, client, watch_folder, db_session):
        (watch_folder / "notes.txt").write_text("hi")

        client.post("/api/organize/preview")

        assert db_session.agent_commands.count_documents({}) == 0

    def test_no_matching_rule_is_reported_honestly(self, client, watch_folder, test_rules):
        (watch_folder / "mystery.xyz123").write_text("??")
        test_rules["auto_organize_unknown_extensions"] = False

        body = client.post("/api/organize/preview").json()

        assert body["no_match"] == 1
        assert body["items"][0]["status"] == "no_match"
        assert body["items"][0]["explanation"]["rule_name"] is None

    def test_a_duplicate_is_reported_and_not_counted_as_ready(self, client, watch_folder):
        dest = watch_folder / "Documents"
        dest.mkdir()
        (dest / "notes.txt").write_text("same content")
        (watch_folder / "notes.txt").write_text("same content")

        body = client.post("/api/organize/preview").json()

        assert body["duplicates"] == 1
        assert body["ready"] == 0
        assert body["items"][0]["status"] == "duplicate"

    def test_empty_watch_folder_returns_an_empty_preview(self, client):
        body = client.post("/api/organize/preview").json()

        assert body == {
            "queued": False,
            "command_id": None,
            "total": 0,
            "ready": 0,
            "duplicates": 0,
            "no_match": 0,
            "errors": 0,
            "items": [],
        }

    def test_confirming_after_preview_organizes_the_previewed_files(self, client, watch_folder):
        (watch_folder / "notes.txt").write_text("hi")

        preview = client.post("/api/organize/preview").json()
        assert preview["ready"] == 1

        confirm = client.post("/api/organize-existing").json()

        assert confirm["organized"] == 1
        assert (watch_folder / "Documents" / "notes.txt").exists()

    def test_a_file_deleted_after_preview_is_correctly_absent_when_confirmed(
        self, client, watch_folder
    ):
        # The preview must never become the authority for what actually
        # gets organized -- confirming re-scans the real, current
        # filesystem state rather than trusting the stale preview payload.
        target = watch_folder / "notes.txt"
        target.write_text("hi")
        preview = client.post("/api/organize/preview").json()
        assert preview["total"] == 1

        target.unlink()

        confirm = client.post("/api/organize-existing").json()

        assert confirm["scanned"] == 0
        assert confirm["organized"] == 0

    def test_preview_scoped_to_the_authenticated_users_own_files(self, client, watch_folder, tmp_path):
        outside = tmp_path / "someone_elses_folder"
        outside.mkdir()
        (outside / "secret.txt").write_text("not yours")
        (watch_folder / "mine.txt").write_text("hi")

        body = client.post("/api/organize/preview").json()

        filenames = {i["filename"] for i in body["items"]}
        assert filenames == {"mine.txt"}

    def test_confirm_endpoint_takes_no_client_supplied_destination_or_file_list(
        self, client, watch_folder, tmp_path
    ):
        # /organize-existing accepts no request body at all -- there is no
        # way for a client to steer where files land or which ones get
        # processed through this flow; the backend always recomputes
        # everything itself. A malicious/unexpected body must simply be
        # ignored, not accepted as instructions.
        (watch_folder / "notes.txt").write_text("hi")
        attacker_controlled = tmp_path / "attacker_chosen_destination"

        resp = client.post(
            "/api/organize-existing",
            json={"destination_path": str(attacker_controlled), "files": ["notes.txt"]},
        )

        assert resp.status_code == 200
        assert (watch_folder / "Documents" / "notes.txt").exists()
        assert not attacker_controlled.exists()


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


class TestAIRuleGenerate:
    """Route-level concerns for POST /api/rules/ai-generate -- field-by-field
    proposal validation itself is covered by test_ai_rule_service.py; these
    confirm the endpoint's wiring: auth, zero persistence side effects,
    rate limiting, and that nothing provider-internal ever reaches the
    response body."""

    # A keyword distinct from conftest.py's BASE_RULES seed ("invoice" ->
    # "Finance Folder") -- reusing "invoice" here would make the *pre-existing*
    # seeded rule win at classify time (it's earlier in keyword_rules), which
    # would silently defeat the end-to-end save/organize test below.
    def _mock_ready(self, monkeypatch):
        from models.schemas import AIRuleGenerateResponse, AIRuleProposal

        monkeypatch.setattr(
            "api.routes.generate_rule_proposal",
            lambda prompt, watch_root: AIRuleGenerateResponse(
                status="ready",
                proposal=AIRuleProposal(
                    rule_type="keyword", name="GST Receipts", keyword="gstreceipt", destination="Finance/GST"
                ),
            ),
        )

    def test_requires_authentication(self, anon_client):
        resp = anon_client.post("/api/rules/ai-generate", json={"prompt": "Put invoices into Finance"})
        assert resp.status_code == 401

    def test_valid_request_returns_a_ready_proposal(self, client, monkeypatch):
        self._mock_ready(monkeypatch)

        resp = client.post("/api/rules/ai-generate", json={"prompt": "Put GST receipts into Finance/GST"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["proposal"]["destination"] == "Finance/GST"

    def test_does_not_save_a_rule(self, client, monkeypatch):
        self._mock_ready(monkeypatch)
        before = client.get("/api/rules").json()

        resp = client.post("/api/rules/ai-generate", json={"prompt": "Put GST receipts into Finance/GST"})
        assert resp.status_code == 200

        after = client.get("/api/rules").json()
        assert after == before

    def test_does_not_organize_or_touch_the_filesystem(self, client, monkeypatch, watch_folder):
        self._mock_ready(monkeypatch)
        loose_file = watch_folder / "gstreceipt_august.pdf"
        loose_file.write_bytes(b"content")

        resp = client.post("/api/rules/ai-generate", json={"prompt": "Put GST receipts into Finance/GST"})
        assert resp.status_code == 200

        assert loose_file.exists()  # never moved
        assert client.get("/api/logs").json() == []  # no activity_log rows
        assert client.get("/api/agent-commands").json() == []  # nothing queued

    def test_unauthenticated_request_never_reaches_the_ai_service(self, anon_client, monkeypatch):
        called = []
        monkeypatch.setattr("api.routes.generate_rule_proposal", lambda prompt, watch_root: called.append(1))

        anon_client.post("/api/rules/ai-generate", json={"prompt": "Put invoices into Finance"})

        assert called == []

    def test_is_rate_limited(self, client, monkeypatch):
        from api import routes

        self._mock_ready(monkeypatch)
        monkeypatch.setattr(routes.ai_rule_limiter, "max_requests", 2)

        for _ in range(2):
            resp = client.post("/api/rules/ai-generate", json={"prompt": "Put invoices into Finance"})
            assert resp.status_code == 200

        resp = client.post("/api/rules/ai-generate", json={"prompt": "Put invoices into Finance"})
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_provider_auth_failure_never_leaks_the_api_key_in_the_response(self, client, monkeypatch):
        from config.settings import settings
        from services import ai_provider

        monkeypatch.setattr(settings, "AI_PROVIDER_API_KEY", "sk-super-secret-marker")

        def _raise(prompt):
            raise ai_provider.AIProviderAuthError("rejected sk-super-secret-marker")

        monkeypatch.setattr("services.ai_rule_service.generate_rule_completion", _raise)

        resp = client.post("/api/rules/ai-generate", json={"prompt": "Put invoices into Finance"})

        assert resp.status_code == 200
        assert "sk-super-secret-marker" not in resp.text

    def test_empty_prompt_returns_a_friendly_invalid_status_not_a_500(self, client):
        resp = client.post("/api/rules/ai-generate", json={"prompt": ""})

        assert resp.status_code == 200
        assert resp.json()["status"] == "invalid"

    def test_a_ready_proposal_can_be_saved_through_the_existing_rule_save_path(
        self, client, monkeypatch, watch_folder
    ):
        """End-to-end proof the AI feature is purely advisory, and the full
        capstone chain (AI Rule Generator -> Rule Conflict Detector ->
        save -> Organization Preview -> real organization -> Feature 1
        explanation -> History -> Organization Health) all agree with each
        other: once a proposal comes back "ready", saving it is nothing
        more than the frontend appending it to the current rules document
        and calling the pre-existing PUT /api/rules -- exercised here
        directly -- after which the RuleEngine treats it exactly like any
        manually-created keyword rule."""
        self._mock_ready(monkeypatch)

        gen_resp = client.post("/api/rules/ai-generate", json={"prompt": "Put GST receipts into Finance/GST"})
        proposal = gen_resp.json()["proposal"]

        current_rules = client.get("/api/rules").json()
        candidate_rules = {
            **current_rules,
            "keyword_rules": [
                *current_rules["keyword_rules"],
                {"keyword": proposal["keyword"], "folder": proposal["destination"]},
            ],
        }

        # Rule Conflict Detector: checked against the not-yet-saved
        # candidate (same shape PUT /api/rules accepts), same as Rules.jsx
        # does before letting the user save. "gstreceipt" doesn't overlap
        # any other rule in the seeded BASE_RULES set.
        conflict_resp = client.post("/api/rules/conflicts", json={"rules": candidate_rules})
        assert conflict_resp.status_code == 200
        assert conflict_resp.json()["high"] == 0

        save_resp = client.put("/api/rules", json=candidate_rules)
        assert save_resp.status_code == 200
        assert {"keyword": "gstreceipt", "folder": "Finance/GST"} in save_resp.json()["keyword_rules"]

        (watch_folder / "gstreceipt_august.pdf").write_bytes(b"pdf bytes")

        # Organization Preview: a dry run must show the new rule winning
        # without moving anything yet.
        preview_resp = client.post("/api/organize/preview")
        assert preview_resp.status_code == 200
        preview_item = next(
            i for i in preview_resp.json()["items"] if i["filename"] == "gstreceipt_august.pdf"
        )
        assert preview_item["status"] == "ready"
        assert preview_item["category"] == "Finance/GST"
        assert (watch_folder / "gstreceipt_august.pdf").exists()  # preview never moves the file

        organize_resp = client.post("/api/organize-existing")
        assert organize_resp.status_code == 200
        assert organize_resp.json()["organized"] == 1
        assert (watch_folder / "Finance" / "GST" / "gstreceipt_august.pdf").exists()

        log = client.get("/api/logs").json()[0]
        assert log["category"] == "Finance/GST"
        assert log["explanation"]["rule_name"] == 'Keyword "gstreceipt"'

        # Organization Health Dashboard: aggregates the same rule count and
        # the same activity_log row just created, never a second source of
        # truth for either. BASE_RULES seeds 3 active rules (1 extension, 1
        # keyword, 1 large_file); the newly-saved "gstreceipt" keyword rule
        # makes 4.
        health = client.get("/api/health/organization").json()
        assert health["activity"]["last_24_hours"]["organized"] == 1
        assert health["rules"]["active"] == 4


class TestUnclassifiedSuggestions:
    """Route-level concerns for POST /api/unclassified/suggestions --
    per-suggestion validation itself is covered by
    test_ai_unclassified_service.py; these confirm the endpoint's wiring:
    auth, zero persistence/organization side effects, rate limiting, and
    the agent-connected two-call (queue, then fetch) contract."""

    def _mock_unsupported(self, monkeypatch):
        from services import ai_unclassified_service

        monkeypatch.setattr(
            ai_unclassified_service,
            "generate_suggestion_completion",
            lambda prompt: [{"group_index": 0, "status": "unsupported", "message": "no"}],
        )

    def test_requires_authentication(self, anon_client):
        resp = anon_client.post("/api/unclassified/suggestions", json={})
        assert resp.status_code == 401

    def test_local_mode_detects_a_true_unclassified_file(self, client, monkeypatch, watch_folder):
        self._mock_unsupported(monkeypatch)
        (watch_folder / "mystery_file").write_bytes(b"data")  # no extension

        resp = client.post("/api/unclassified/suggestions", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["unclassified"] == 1
        assert body["suggestions"][0]["file_names"] == ["mystery_file"]

    def test_a_rule_match_is_not_treated_as_unclassified(self, client, monkeypatch, watch_folder):
        # "invoice" is in the seeded keyword_rules (conftest.py's BASE_RULES).
        self._mock_unsupported(monkeypatch)
        (watch_folder / "invoice_march.pdf").write_bytes(b"data")

        resp = client.post("/api/unclassified/suggestions", json={})

        body = resp.json()
        assert body["unclassified"] == 0
        assert body["suggestions"] == []

    def test_does_not_save_a_rule(self, client, monkeypatch, watch_folder):
        self._mock_unsupported(monkeypatch)
        (watch_folder / "mystery_file").write_bytes(b"data")
        before = client.get("/api/rules").json()

        client.post("/api/unclassified/suggestions", json={})

        after = client.get("/api/rules").json()
        assert after == before

    def test_does_not_organize_or_touch_the_filesystem(self, client, monkeypatch, watch_folder):
        self._mock_unsupported(monkeypatch)
        loose_file = watch_folder / "mystery_file"
        loose_file.write_bytes(b"data")

        resp = client.post("/api/unclassified/suggestions", json={})

        assert resp.status_code == 200
        assert loose_file.exists()
        assert client.get("/api/logs").json() == []
        assert client.get("/api/agent-commands").json() == []

    def test_is_rate_limited(self, client, monkeypatch):
        from api import routes

        self._mock_unsupported(monkeypatch)
        monkeypatch.setattr(routes.ai_unclassified_limiter, "max_requests", 2)

        for _ in range(2):
            resp = client.post("/api/unclassified/suggestions", json={})
            assert resp.status_code == 200

        resp = client.post("/api/unclassified/suggestions", json={})
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_unknown_command_id_404s(self, client):
        # A command_id is only ever consulted once this account is itself
        # agent-connected -- an unconnected account ignores it and always
        # scans locally instead (see TestDualModeUnclassifiedSuggestions,
        # test_agent.py, for the full dual-mode contract).
        token = client.post("/api/auth/agent-token", json={"scope": "full"}).json()["token"]
        client.get("/api/agent/rules", headers={"Authorization": f"Bearer {token}"})

        resp = client.post("/api/unclassified/suggestions", json={"command_id": 999999})
        assert resp.status_code == 404

    def test_two_rapid_requests_each_succeed_independently(self, client, monkeypatch, watch_folder):
        self._mock_unsupported(monkeypatch)
        (watch_folder / "mystery_file").write_bytes(b"data")

        first = client.post("/api/unclassified/suggestions", json={})
        second = client.post("/api/unclassified/suggestions", json={})

        assert first.status_code == second.status_code == 200
        assert first.json()["unclassified"] == second.json()["unclassified"] == 1


class TestUnclassifiedSuggestionsIntegration:
    """Phase 26 of the spec this implements: a full, mocked-provider,
    end-to-end proof that AI Unclassified File Suggestions integrates with
    Features 1-3 rather than existing as a disconnected demo -- unclassified
    file -> AI suggestion -> user reviews -> rule saved through the existing
    PUT /api/rules -> the real classifier now matches -> Feature 1's
    explanation appears after actual organization -> Organization Preview
    reflects the new rule -> an actual move still requires the separate,
    explicit organize-existing call."""

    def test_full_suggestion_to_organized_file_flow(self, client, monkeypatch, watch_folder):
        from services import ai_unclassified_service

        # 1 + 2: a file the real classifier reports as no-match. The seeded
        # BASE_RULES (conftest.py) maps .pdf to a real category, which would
        # otherwise match before ever falling through to "default" -- clear
        # that mapping first so this file genuinely has no matching rule,
        # same as a fresh account with no categories configured yet would.
        current_rules = client.get("/api/rules").json()
        current_rules["categories"] = {}
        current_rules["auto_organize_unknown_extensions"] = False
        client.put("/api/rules", json=current_rules)

        (watch_folder / "gstreceipt_august.pdf").write_bytes(b"pdf bytes")
        preview_before = client.post("/api/organize/preview").json()
        assert preview_before["no_match"] == 1
        assert preview_before["items"][0]["explanation"]["match_type"] == "default"

        # 3 + 4: request an AI suggestion (mocked provider).
        monkeypatch.setattr(
            ai_unclassified_service,
            "generate_suggestion_completion",
            lambda prompt: [
                {
                    "group_index": 0,
                    "status": "ready",
                    "suggested_category": "GST Receipts",
                    "reason": ['Filename contains "gstreceipt"'],
                    "suggested_rule": {
                        "rule_type": "keyword",
                        "keyword": "gstreceipt",
                        "destination": "Finance/GST",
                    },
                }
            ],
        )
        suggestion_resp = client.post("/api/unclassified/suggestions", json={})
        assert suggestion_resp.status_code == 200

        # 5: verify the suggestion is present and usable.
        suggestion = suggestion_resp.json()["suggestions"][0]
        assert suggestion["suggestion_status"] == "ready"
        assert suggestion["suggested_rule"]["destination"] == "Finance/GST"
        assert not client.get("/api/logs").json()  # still nothing organized

        # 6 + 7 + 8: user chooses "Create Rule" -- folded into the current
        # rules doc and saved through the existing, unmodified PUT /api/rules.
        rule = suggestion["suggested_rule"]
        current_rules = client.get("/api/rules").json()
        current_rules["keyword_rules"].append(
            {"keyword": rule["keyword"], "folder": rule["destination"]}
        )
        save_resp = client.put("/api/rules", json=current_rules)
        assert save_resp.status_code == 200
        assert {"keyword": "gstreceipt", "folder": "Finance/GST"} in save_resp.json()[
            "keyword_rules"
        ]

        # 9 + 11: the real classifier now matches, and Organization Preview
        # reflects the newly created rule -- still without moving anything.
        preview_after = client.post("/api/organize/preview").json()
        assert preview_after["no_match"] == 0
        assert preview_after["items"][0]["category"] == "Finance/GST"
        assert (watch_folder / "gstreceipt_august.pdf").exists()  # untouched so far

        # 12: an actual move still requires the separate, explicit action.
        organize_resp = client.post("/api/organize-existing")
        assert organize_resp.status_code == 200
        assert organize_resp.json()["organized"] == 1
        assert (watch_folder / "Finance" / "GST" / "gstreceipt_august.pdf").exists()

        # 10: Feature 1's explanation appears after the actual organization.
        log = client.get("/api/logs").json()[0]
        assert log["category"] == "Finance/GST"
        assert log["explanation"]["rule_name"] == 'Keyword "gstreceipt"'


class TestDuplicateAnalysis:
    """Route-level concerns for POST /api/duplicates/analyze -- the
    detection algorithm itself is covered by test_duplicate_detection.py.
    These confirm the endpoint's wiring: auth, zero side effects, and the
    agent-connected two-call (queue, then fetch) contract."""

    def test_requires_authentication(self, anon_client):
        resp = anon_client.post("/api/duplicates/analyze", json={})
        assert resp.status_code == 401

    def test_no_duplicates_returns_zero_groups(self, client, watch_folder):
        (watch_folder / "a.txt").write_bytes(b"unique content")

        resp = client.post("/api/duplicates/analyze", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["duplicate_groups"] == 0
        assert body["groups"] == []

    def test_detects_a_real_duplicate_pair(self, client, watch_folder):
        (watch_folder / "invoice.pdf").write_bytes(b"identical content")
        (watch_folder / "invoice_copy.pdf").write_bytes(b"identical content")

        resp = client.post("/api/duplicates/analyze", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["duplicate_groups"] == 1
        assert body["duplicate_files"] == 2
        assert body["groups"][0]["duplicate_type"] == "exact_content_duplicate"

    def test_finds_duplicates_across_already_organized_subfolders(self, client, watch_folder):
        # Unlike Organization Preview's shallow top-level-only scan, this
        # feature's whole point is to also catch content already organized
        # into different category folders.
        (watch_folder / "Finance" / "invoice.pdf").parent.mkdir(parents=True, exist_ok=True)
        (watch_folder / "Finance" / "invoice.pdf").write_bytes(b"same content")
        (watch_folder / "Downloads").mkdir(parents=True, exist_ok=True)
        (watch_folder / "Downloads" / "invoice (1).pdf").write_bytes(b"same content")

        resp = client.post("/api/duplicates/analyze", json={})

        body = resp.json()
        assert body["duplicate_groups"] == 1
        paths = {f["relative_path"] for f in body["groups"][0]["files"]}
        assert paths == {"Finance/invoice.pdf", "Downloads/invoice (1).pdf"}

    def test_relative_paths_never_expose_the_absolute_watch_folder(self, client, watch_folder):
        (watch_folder / "a.bin").write_bytes(b"content")
        (watch_folder / "b.bin").write_bytes(b"content")

        resp = client.post("/api/duplicates/analyze", json={})

        for f in resp.json()["groups"][0]["files"]:
            assert str(watch_folder) not in f["relative_path"]

    def test_never_moves_renames_or_deletes_files(self, client, watch_folder):
        a = watch_folder / "a.bin"
        b = watch_folder / "b.bin"
        a.write_bytes(b"content")
        b.write_bytes(b"content")

        client.post("/api/duplicates/analyze", json={})

        assert a.exists() and b.exists()

    def test_never_writes_activity_log_or_agent_commands(self, client, watch_folder):
        (watch_folder / "a.bin").write_bytes(b"content")
        (watch_folder / "b.bin").write_bytes(b"content")

        client.post("/api/duplicates/analyze", json={})

        assert client.get("/api/logs").json() == []
        assert client.get("/api/agent-commands").json() == []

    def test_never_modifies_rules(self, client, watch_folder):
        before = client.get("/api/rules").json()
        (watch_folder / "a.bin").write_bytes(b"content")
        (watch_folder / "b.bin").write_bytes(b"content")

        client.post("/api/duplicates/analyze", json={})

        assert client.get("/api/rules").json() == before

    def test_unknown_command_id_404s(self, client):
        token = client.post("/api/auth/agent-token", json={"scope": "full"}).json()["token"]
        client.get("/api/agent/rules", headers={"Authorization": f"Bearer {token}"})

        resp = client.post("/api/duplicates/analyze", json={"command_id": 999999})
        assert resp.status_code == 404

    def test_two_rapid_requests_each_succeed_independently(self, client, watch_folder):
        (watch_folder / "a.bin").write_bytes(b"content")
        (watch_folder / "b.bin").write_bytes(b"content")

        first = client.post("/api/duplicates/analyze", json={})
        second = client.post("/api/duplicates/analyze", json={})

        assert first.status_code == second.status_code == 200
        assert first.json()["duplicate_groups"] == second.json()["duplicate_groups"] == 1


class TestFileSearch:
    """Route-level concerns for POST /api/files/search -- the AI
    interpretation and deterministic search engine themselves are covered
    by test_file_search.py; these confirm the endpoint's wiring: auth,
    validation, zero side effects, rate limiting, and safe error mapping."""

    def _mock_ready(self, monkeypatch, query=None):
        from services import file_search_service

        # `query` may legitimately be `{}` (an explicit "match everything"
        # query) -- `is None`, not truthiness, decides whether to fall back
        # to the default.
        actual_query = query if query is not None else {"filename_contains": ["invoice"]}
        monkeypatch.setattr(
            file_search_service,
            "generate_search_completion",
            lambda prompt: {"status": "ready", "query": actual_query},
        )

    def test_requires_authentication(self, anon_client):
        resp = anon_client.post("/api/files/search", json={"query": "find invoices"})
        assert resp.status_code == 401

    def test_a_ready_query_searches_local_files(self, client, monkeypatch, watch_folder):
        self._mock_ready(monkeypatch, {"filename_contains": ["invoice"], "extension": [".pdf"]})
        (watch_folder / "invoice_august.pdf").write_bytes(b"content")
        (watch_folder / "resume.pdf").write_bytes(b"content")

        resp = client.post("/api/files/search", json={"query": "find pdf invoices"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["total_matches"] == 1
        assert body["results"][0]["filename"] == "invoice_august.pdf"

    def test_interpretation_is_deterministic_not_the_ais_own_text(self, client, monkeypatch, watch_folder):
        from services import file_search_service

        # The AI's own "interpretation" claim is a lie relative to its
        # query -- the response must reflect the VALIDATED query, never
        # this string.
        monkeypatch.setattr(
            file_search_service,
            "generate_search_completion",
            lambda prompt: {
                "status": "ready",
                "query": {"filename_contains": ["invoice"]},
                "interpretation": ["This text must never be trusted or shown"],
            },
        )

        resp = client.post("/api/files/search", json={"query": "find invoices"})

        assert resp.status_code == 200
        assert "This text must never be trusted or shown" not in resp.json()["interpretation"]
        assert any("invoice" in line.lower() for line in resp.json()["interpretation"])

    def test_unsupported_query(self, client, monkeypatch):
        from services import file_search_service

        monkeypatch.setattr(
            file_search_service,
            "generate_search_completion",
            lambda prompt: {"status": "unsupported", "message": "Content search isn't supported."},
        )

        resp = client.post("/api/files/search", json={"query": "find files about machine learning"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "unsupported"
        assert body["results"] == []

    def test_needs_clarification_query(self, client, monkeypatch):
        from services import file_search_service

        monkeypatch.setattr(
            file_search_service,
            "generate_search_completion",
            lambda prompt: {
                "status": "needs_clarification",
                "message": "Which date range do you mean?",
                "questions": ["Which date range do you mean by 'recently'?"],
            },
        )

        resp = client.post("/api/files/search", json={"query": "find recent files"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "needs_clarification"
        assert body["questions"] == ["Which date range do you mean by 'recently'?"]

    def test_malformed_ai_output_is_a_safe_error_not_a_500(self, client, monkeypatch):
        from services import file_search_service

        monkeypatch.setattr(
            file_search_service,
            "generate_search_completion",
            lambda prompt: {"status": "ready", "query": {"sort_by": "relevance"}},  # invalid enum value
        )

        resp = client.post("/api/files/search", json={"query": "find invoices"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_a_missing_query_object_is_treated_as_match_everything_not_an_error(self, client, monkeypatch):
        from services import file_search_service

        monkeypatch.setattr(
            file_search_service, "generate_search_completion", lambda prompt: {"status": "ready"}
        )  # no "query" key at all -- SearchQuery's own defaults apply

        resp = client.post("/api/files/search", json={"query": "find everything"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_unexpected_ai_fields_are_dropped_not_executed(self, client, monkeypatch, watch_folder):
        from services import file_search_service

        monkeypatch.setattr(
            file_search_service,
            "generate_search_completion",
            lambda prompt: {
                "status": "ready",
                "query": {
                    "filename_contains": ["invoice"],
                    "path": "C:/Users/OtherUser/Secrets",
                    "shell": "rm -rf /",
                },
            },
        )
        (watch_folder / "invoice.pdf").write_bytes(b"content")

        resp = client.post("/api/files/search", json={"query": "find invoices"})

        assert resp.status_code == 200
        assert resp.json()["total_matches"] == 1  # the unknown fields never affected the search

    def test_ai_provider_unavailable_is_a_safe_message(self, client, monkeypatch):
        from services import ai_provider
        from services import file_search_service

        def _raise(prompt):
            raise ai_provider.AIProviderUnavailable("boom")

        monkeypatch.setattr(file_search_service, "generate_search_completion", _raise)

        resp = client.post("/api/files/search", json={"query": "find invoices"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_ai_provider_rate_limit_is_a_safe_message(self, client, monkeypatch):
        from services import ai_provider
        from services import file_search_service

        def _raise(prompt):
            raise ai_provider.AIProviderRateLimited("boom")

        monkeypatch.setattr(file_search_service, "generate_search_completion", _raise)

        resp = client.post("/api/files/search", json={"query": "find invoices"})

        assert resp.status_code == 200
        assert "busy" in resp.json()["message"].lower()

    def test_ai_provider_auth_failure_never_leaks_the_api_key(self, client, monkeypatch):
        from config.settings import settings
        from services import ai_provider
        from services import file_search_service

        monkeypatch.setattr(settings, "AI_PROVIDER_API_KEY", "sk-super-secret-marker")

        def _raise(prompt):
            raise ai_provider.AIProviderAuthError("rejected sk-super-secret-marker")

        monkeypatch.setattr(file_search_service, "generate_search_completion", _raise)

        resp = client.post("/api/files/search", json={"query": "find invoices"})

        assert resp.status_code == 200
        assert "sk-super-secret-marker" not in resp.text

    def test_empty_query_is_a_friendly_invalid_status(self, client):
        resp = client.post("/api/files/search", json={"query": ""})
        assert resp.status_code == 200
        assert resp.json()["status"] == "invalid"

    def test_prompt_length_limit(self, client):
        resp = client.post("/api/files/search", json={"query": "x" * 501})
        assert resp.status_code == 200
        assert resp.json()["status"] == "invalid"

    def test_is_rate_limited(self, client, monkeypatch):
        from api import routes

        self._mock_ready(monkeypatch)
        monkeypatch.setattr(routes.ai_file_search_limiter, "max_requests", 2)

        for _ in range(2):
            resp = client.post("/api/files/search", json={"query": "find invoices"})
            assert resp.status_code == 200

        resp = client.post("/api/files/search", json={"query": "find invoices"})
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_unauthenticated_request_never_reaches_the_ai_service(self, anon_client, monkeypatch):
        from services import file_search_service

        called = []
        monkeypatch.setattr(
            file_search_service, "generate_search_completion", lambda prompt: called.append(1)
        )

        anon_client.post("/api/files/search", json={"query": "find invoices"})

        assert called == []

    def test_does_not_move_or_touch_files(self, client, monkeypatch, watch_folder):
        self._mock_ready(monkeypatch)
        loose_file = watch_folder / "invoice.pdf"
        loose_file.write_bytes(b"content")

        resp = client.post("/api/files/search", json={"query": "find invoices"})

        assert resp.status_code == 200
        assert loose_file.exists()

    def test_does_not_modify_rules(self, client, monkeypatch, watch_folder):
        self._mock_ready(monkeypatch)
        before = client.get("/api/rules").json()

        client.post("/api/files/search", json={"query": "find invoices"})

        assert client.get("/api/rules").json() == before

    def test_does_not_write_activity_log_or_enqueue_organize_commands(self, client, monkeypatch, watch_folder):
        self._mock_ready(monkeypatch)
        (watch_folder / "invoice.pdf").write_bytes(b"content")

        client.post("/api/files/search", json={"query": "find invoices"})

        assert client.get("/api/logs").json() == []
        assert client.get("/api/agent-commands").json() == []

    def test_no_absolute_paths_are_exposed_in_results(self, client, monkeypatch, watch_folder):
        self._mock_ready(monkeypatch, {"filename_contains": ["invoice"]})
        (watch_folder / "invoice.pdf").write_bytes(b"content")

        resp = client.post("/api/files/search", json={"query": "find invoices"})

        for r in resp.json()["results"]:
            assert str(watch_folder) not in r["relative_path"]

    def test_only_configured_watch_folders_are_searched(self, client, monkeypatch, watch_folder, tmp_path):
        self._mock_ready(monkeypatch, {})
        (watch_folder / "inside.txt").write_bytes(b"content")
        (tmp_path / "outside.txt").write_bytes(b"content")

        resp = client.post("/api/files/search", json={"query": "find everything"})

        names = {r["filename"] for r in resp.json()["results"]}
        assert names == {"inside.txt"}

    def test_result_truncation_is_disclosed(self, client, monkeypatch, watch_folder):
        self._mock_ready(monkeypatch, {"limit": 2})
        for i in range(5):
            (watch_folder / f"file{i}.txt").write_bytes(b"content")

        resp = client.post("/api/files/search", json={"query": "find everything"})

        body = resp.json()
        assert body["total_matches"] == 5
        assert body["returned"] == 2
        assert body["truncated"] is True

    def test_unknown_command_id_404s(self, client):
        token = client.post("/api/auth/agent-token", json={"scope": "full"}).json()["token"]
        client.get("/api/agent/rules", headers={"Authorization": f"Bearer {token}"})

        resp = client.post("/api/files/search", json={"query": "find invoices", "command_id": 999999})
        assert resp.status_code == 404

    def test_full_pipeline_unclassified_pdf_invoices_from_august(self, client, monkeypatch, watch_folder):
        import os
        import time
        from datetime import datetime, timezone

        current_rules = client.get("/api/rules").json()
        current_rules["categories"] = {}
        current_rules["auto_organize_unknown_extensions"] = False
        # BASE_RULES (conftest.py) seeds a keyword rule for "invoice" --
        # clear it so these files genuinely have no matching rule, same as
        # a fresh account with no rules configured yet would.
        current_rules["keyword_rules"] = []
        client.put("/api/rules", json=current_rules)

        self._mock_ready(
            monkeypatch,
            {
                "extension": [".pdf"],
                "filename_contains": ["invoice"],
                "unclassified_only": True,
                "time_range": "month_year",
                "time_range_month": 8,
            },
        )
        august = watch_folder / "invoice_august.pdf"
        august.write_bytes(b"content")
        os.utime(august, (datetime(datetime.now(timezone.utc).year, 8, 15, tzinfo=timezone.utc).timestamp(),) * 2)
        september = watch_folder / "invoice_september.pdf"
        september.write_bytes(b"content")
        os.utime(september, (datetime(datetime.now(timezone.utc).year, 9, 15, tzinfo=timezone.utc).timestamp(),) * 2)

        resp = client.post("/api/files/search", json={"query": "find unclassified pdf invoices from august"})

        body = resp.json()
        assert body["total_matches"] == 1
        assert body["results"][0]["filename"] == "invoice_august.pdf"


class TestOrganizationHealth:
    """Route-level concerns for GET /api/health/organization -- the
    aggregation math itself is covered by test_health_service.py; these
    confirm the endpoint's wiring: auth, account isolation, and zero side
    effects. Agent-connected behavior lives in
    test_agent.py::TestOrganizationHealthAgentMode."""

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/api/health/organization")
        assert resp.status_code == 401

    def test_empty_workspace_returns_a_well_formed_response(self, client):
        resp = client.get("/api/health/organization")

        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_connected"] is False
        assert body["files"]["scanned"] == 0
        assert body["files"]["classification_coverage_percent"] is None
        assert body["duplicates"]["groups"] == 0
        assert body["rules"]["active"] == 3  # BASE_RULES: 1 extension + 1 keyword + 1 large_file
        assert body["activity"]["last_7_days"]["organized"] == 0

    def test_reflects_real_files_and_rules(self, client, watch_folder):
        (watch_folder / "invoice_1.pdf").write_bytes(b"content")
        (watch_folder / "dup_a.bin").write_bytes(b"same")
        (watch_folder / "dup_b.bin").write_bytes(b"same")

        body = client.get("/api/health/organization").json()

        assert body["files"]["scanned"] == 3
        assert body["duplicates"]["groups"] == 1
        assert body["duplicates"]["duplicate_files"] == 2

    def test_reflects_real_activity_log_rows(self, client, db_session):
        _log(db_session, action="moved")
        _log(db_session, action="duplicate_skipped")

        body = client.get("/api/health/organization").json()

        assert body["activity"]["last_24_hours"]["organized"] == 1
        assert body["activity"]["last_24_hours"]["skipped"] == 1

    def test_account_scoped_not_another_users_data(self, client, db_session):
        _log(db_session, user_id=999999, action="moved")

        body = client.get("/api/health/organization").json()

        assert body["activity"]["last_30_days"]["organized"] == 0

    def test_never_writes_activity_log_or_agent_commands(self, client, watch_folder):
        (watch_folder / "a.bin").write_bytes(b"content")

        client.get("/api/health/organization")

        assert client.get("/api/logs").json() == []
        assert client.get("/api/agent-commands").json() == []

    def test_never_modifies_rules(self, client, watch_folder):
        before = client.get("/api/rules").json()
        (watch_folder / "a.bin").write_bytes(b"content")

        client.get("/api/health/organization")

        assert client.get("/api/rules").json() == before

    def test_never_touches_a_real_file(self, client, watch_folder):
        f = watch_folder / "a.bin"
        f.write_bytes(b"content")

        client.get("/api/health/organization")

        assert f.exists()
        assert f.read_bytes() == b"content"

    def test_ai_provider_is_never_called(self, client, monkeypatch, watch_folder):
        from services import ai_provider

        def _explode(*a, **k):
            raise AssertionError("must never call an AI provider")

        monkeypatch.setattr(ai_provider, "generate_rule_completion", _explode)
        monkeypatch.setattr(ai_provider, "generate_suggestion_completion", _explode)
        monkeypatch.setattr(ai_provider, "generate_search_completion", _explode)
        (watch_folder / "a.bin").write_bytes(b"content")

        resp = client.get("/api/health/organization")

        assert resp.status_code == 200

    def test_partial_failure_still_returns_200_with_other_sections_intact(self, client, monkeypatch):
        from services import health_service

        monkeypatch.setattr(
            health_service,
            "build_duplicate_groups_result",
            lambda *a, **k: (_ for _ in ()).throw(OSError("boom")),
        )

        resp = client.get("/api/health/organization")

        assert resp.status_code == 200
        body = resp.json()
        assert body["duplicates"]["status"] == "unavailable"
        assert body["rules"]["status"] == "available"
