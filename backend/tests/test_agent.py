import hashlib

import pytest
from fastapi.testclient import TestClient

from config.agent_release import AGENT_LATEST_VERSION, AGENT_RELEASE_PATH, agent_release_sha256
from main import app
from tests.test_routes import _log, client  # noqa: F401 -- reused fixtures


def _agent_headers(client, scope="full"):
    token = client.post("/api/auth/agent-token", json={"scope": scope}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _connect_agent(client):
    """Gives this account a fresh agent_last_seen_at heartbeat, same as a
    real agent's first poll would -- routes.py's dual-mode branches key off
    exactly this."""
    client.get("/api/agent/rules", headers=_agent_headers(client))


class TestAgentRules:
    def test_matches_the_browser_facing_rules_shape(self, client):
        headers = _agent_headers(client)
        browser_rules = client.get("/api/rules").json()
        agent_rules = client.get("/api/agent/rules", headers=headers).json()
        assert agent_rules == browser_rules

    def test_rejects_a_missing_token(self, client):
        resp = client.get("/api/agent/rules")
        assert resp.status_code == 401


class TestAgentTokenScope:
    def test_read_only_token_can_read_rules(self, client):
        headers = _agent_headers(client, scope="read_only")
        resp = client.get("/api/agent/rules", headers=headers)
        assert resp.status_code == 200

    def test_read_only_token_cannot_report_activity(self, client):
        headers = _agent_headers(client, scope="read_only")
        resp = client.post(
            "/api/agent/activity",
            headers=headers,
            json={
                "original_filename": "report.pdf",
                "final_filename": "report.pdf",
                "source_path": "C:/local/report.pdf",
                "destination_path": "C:/local/Documents/report.pdf",
                "category": "Documents",
                "action": "moved",
                "file_size": 1234,
                "file_hash": "abc123",
            },
        )
        assert resp.status_code == 403

    def test_read_only_token_cannot_pull_commands(self, client):
        headers = _agent_headers(client, scope="read_only")
        resp = client.get("/api/agent/commands", headers=headers)
        assert resp.status_code == 403

    def test_read_only_token_cannot_complete_commands(self, client):
        headers = _agent_headers(client, scope="read_only")
        resp = client.post(
            "/api/agent/commands/1/complete", headers=headers, json={"success": True}
        )
        assert resp.status_code == 403

    def test_full_token_can_still_do_everything_read_only_cannot(self, client):
        headers = _agent_headers(client, scope="full")
        assert client.get("/api/agent/commands", headers=headers).status_code == 200

    def test_a_token_minted_before_scoping_existed_still_has_full_access(self, client):
        # Simulates a real installed agent's already-saved token from
        # before this feature shipped: no "scope" claim in the payload at
        # all, not an empty/default one -- get_current_agent must treat
        # that the same as "full", or every agent in the field would be
        # silently downgraded to read-only the moment the backend updates.
        from api.auth import create_agent_token

        user_id = client.get("/api/auth/me").json()["id"]
        old_style_token = create_agent_token(user_id, token_version=0)
        headers = {"Authorization": f"Bearer {old_style_token}"}
        assert client.get("/api/agent/commands", headers=headers).status_code == 200


class TestAgentActivity:
    def test_reported_activity_is_visible_to_the_browser(self, client):
        headers = _agent_headers(client)
        resp = client.post(
            "/api/agent/activity",
            headers=headers,
            json={
                "original_filename": "report.pdf",
                "final_filename": "report.pdf",
                "source_path": "C:/local/report.pdf",
                "destination_path": "C:/local/Documents/report.pdf",
                "category": "Documents",
                "action": "moved",
                "file_size": 1234,
                "file_hash": "abc123",
            },
        )
        assert resp.status_code == 200

        logs = client.get("/api/logs").json()
        assert any(log["final_filename"] == "report.pdf" for log in logs)

    def test_a_report_with_no_explanation_field_still_works_old_agent_compat(self, client):
        # An older agent build (before this field existed) posts no
        # `explanation` key at all -- must still succeed, not a validation
        # error, and the row reads back with a plain null.
        headers = _agent_headers(client)
        resp = client.post(
            "/api/agent/activity",
            headers=headers,
            json={
                "original_filename": "old_agent_report.pdf",
                "final_filename": "old_agent_report.pdf",
                "source_path": "C:/local/old_agent_report.pdf",
                "destination_path": "C:/local/Documents/old_agent_report.pdf",
                "category": "Documents",
                "action": "moved",
                "file_size": 100,
                "file_hash": "cafef00d",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["explanation"] is None

        logs = client.get("/api/logs").json()
        reported = next(log for log in logs if log["final_filename"] == "old_agent_report.pdf")
        assert reported["explanation"] is None

    def test_reported_activity_carries_the_agents_own_classification_explanation(self, client):
        headers = _agent_headers(client)
        resp = client.post(
            "/api/agent/activity",
            headers=headers,
            json={
                "original_filename": "invoice.pdf",
                "final_filename": "invoice.pdf",
                "source_path": "C:/local/invoice.pdf",
                "destination_path": "C:/local/Finance/invoice.pdf",
                "category": "Finance",
                "action": "moved",
                "file_size": 1234,
                "file_hash": "abc123",
                "explanation": {
                    "match_type": "keyword",
                    "matched_value": "invoice",
                    "destination": "Finance",
                    "rule_name": 'Keyword "invoice"',
                    "priority": 1,
                },
            },
        )
        assert resp.status_code == 200
        assert resp.json()["explanation"]["match_type"] == "keyword"

        logs = client.get("/api/logs").json()
        reported = next(log for log in logs if log["final_filename"] == "invoice.pdf")
        assert reported["explanation"]["matched_value"] == "invoice"

    def test_multiple_plain_logs_without_client_ref_can_coexist_for_one_user(self, client, db_session):
        """Regression test: the (user_id, client_ref) unique index must
        never block ordinary, non-agent-reported activity_log rows (the
        vast majority of them) from piling up for the same user. A first
        attempt at this index used `sparse=True` on a compound key, which
        only excludes a document when *every* indexed field is missing --
        since user_id is never missing, that sparse flag did nothing, and
        creating the index against real data crashed the backend outright
        with a duplicate-key error the moment a second such row existed."""
        first = _log(db_session, user_id=1)
        second = _log(db_session, user_id=1)
        assert first.id != second.id
        assert "client_ref" not in first
        assert "client_ref" not in second

    def test_retried_report_with_the_same_client_ref_is_not_duplicated(self, client, db_session):
        headers = _agent_headers(client)
        payload = {
            "original_filename": "invoice.pdf",
            "final_filename": "invoice.pdf",
            "source_path": "C:/local/invoice.pdf",
            "destination_path": "C:/local/Finance/invoice.pdf",
            "category": "Finance",
            "action": "moved",
            "file_size": 42,
            "file_hash": "deadbeef",
            "client_ref": "agent-outbox-row-1",
        }

        first = client.post("/api/agent/activity", headers=headers, json=payload)
        second = client.post("/api/agent/activity", headers=headers, json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]

        matches = list(
            db_session.activity_log.find({"client_ref": "agent-outbox-row-1"})
        )
        assert len(matches) == 1


class TestDualModeUndo:
    def test_without_an_agent_undo_runs_locally_as_before(self, client, db_session, watch_folder):
        dest = watch_folder / "Documents" / "a.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("hi")
        _log(db_session, destination_path=str(dest), source_path=str(watch_folder / "a.txt"))

        resp = client.post("/api/undo")

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is False
        assert body["success"] is True

    def test_with_an_agent_connected_undo_is_queued_not_executed(
        self, client, db_session, watch_folder
    ):
        dest = watch_folder / "Documents" / "b.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("hi")
        log = _log(db_session, destination_path=str(dest), source_path=str(watch_folder / "b.txt"))

        _connect_agent(client)
        resp = client.post("/api/undo")

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is True
        assert body["success"] is True
        # The claim already happened (concurrency guarantee), but the actual
        # move did not -- the file must still be sitting at its destination.
        assert dest.exists()

        commands = client.get(
            "/api/agent/commands", headers=_agent_headers(client)
        ).json()
        assert any(c["type"] == "undo" and c["payload"]["log_id"] == log.id for c in commands)

    def test_agent_reporting_failure_releases_the_claim(self, client, db_session, watch_folder):
        dest = watch_folder / "Documents" / "c.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("hi")
        log = _log(db_session, destination_path=str(dest), source_path=str(watch_folder / "c.txt"))

        _connect_agent(client)
        client.post("/api/undo")
        # Minted last, deliberately -- issuing a token regenerates it and
        # invalidates any previously-issued one, so this has to happen
        # after every other call in this test that also mints one.
        headers = _agent_headers(client)

        command = next(
            c for c in client.get("/api/agent/commands", headers=headers).json()
            if c["payload"]["log_id"] == log.id
        )
        complete_resp = client.post(
            f"/api/agent/commands/{command['id']}/complete",
            headers=headers,
            json={"success": False, "error": "file not found"},
        )
        assert complete_resp.status_code == 200

        refreshed = db_session.activity_log.find_one({"_id": log.id})
        assert refreshed["undone"] is False

        remaining = client.get("/api/agent/commands", headers=headers).json()
        assert all(c["id"] != command["id"] for c in remaining)


class TestDualModeReclassify:
    def test_with_an_agent_connected_reclassify_is_queued(self, client, db_session, watch_folder):
        dest = watch_folder / "Documents" / "d.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("hi")
        log = _log(db_session, destination_path=str(dest), source_path=str(watch_folder / "d.txt"))

        _connect_agent(client)
        resp = client.post(f"/api/logs/{log.id}/reclassify", json={"category": "Archive"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is True
        # Nothing moved -- still sitting exactly where it was.
        assert dest.exists()

        commands = client.get("/api/agent/commands", headers=_agent_headers(client)).json()
        assert any(c["type"] == "reclassify" and c["payload"]["category"] == "Archive" for c in commands)

    def test_completing_the_same_command_twice_is_safe(self, client, db_session, watch_folder):
        """Documents an invariant agent/outbox.py's retry logic depends on:
        an at-least-once delivery of the SAME completion body must never
        double-apply its side effect. Every write in complete_command() is
        a plain $set, so this should already hold -- this test exists so a
        future change that breaks that (e.g. switching to $push or an
        increment) fails loudly here instead of silently in production."""
        dest = watch_folder / "Documents" / "e.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("hi")
        log = _log(db_session, destination_path=str(dest), source_path=str(watch_folder / "e.txt"))

        _connect_agent(client)
        client.post(f"/api/logs/{log.id}/reclassify", json={"category": "Archive"})
        headers = _agent_headers(client)
        command = next(
            c for c in client.get("/api/agent/commands", headers=headers).json()
            if c["type"] == "reclassify"
        )
        body = {
            "success": True,
            "result": {"destination_path": str(watch_folder / "Archive" / "e.txt")},
        }

        first = client.post(
            f"/api/agent/commands/{command['id']}/complete", headers=headers, json=body
        )
        second = client.post(
            f"/api/agent/commands/{command['id']}/complete", headers=headers, json=body
        )

        assert first.status_code == 200
        assert second.status_code == 200
        refreshed = db_session.activity_log.find_one({"_id": log.id})
        assert refreshed["category"] == "Archive"
        assert refreshed["destination_path"] == str(watch_folder / "Archive" / "e.txt")

    def test_completing_a_nonexistent_command_id_is_a_404(self, client):
        headers = _agent_headers(client)

        resp = client.post(
            "/api/agent/commands/999999/complete", headers=headers, json={"success": True}
        )

        assert resp.status_code == 404

    def test_completing_another_users_command_is_a_404_not_a_leak(
        self, client, db_session, watch_folder
    ):
        """complete_command()'s lookup is {"_id": command_id, "user_id":
        user["id"]} -- scoped from the authenticated agent's own account,
        never a client-supplied value. A command_id that's real but belongs
        to a different account must be indistinguishable from one that
        doesn't exist at all, not silently completable or informative
        about its existence."""
        other = TestClient(app)
        other_resp = other.post(
            "/api/auth/register", json={"email": "other-agent-user@example.com", "password": "test-password-123"}
        )
        assert other_resp.status_code == 201
        other_user_id = other_resp.json()["id"]
        db_session.users.update_one({"_id": other_user_id}, {"$set": {"watch_folder": str(watch_folder)}})
        _connect_agent(other)
        other.post("/api/organize-existing")
        # Minted last, deliberately -- issuing a token regenerates it and
        # invalidates any previously-issued one (same pattern as every
        # other test in this file).
        other_headers = _agent_headers(other)
        other_command = next(
            c for c in other.get("/api/agent/commands", headers=other_headers).json()
            if c["type"] == "organize_existing"
        )

        headers = _agent_headers(client)
        resp = client.post(
            f"/api/agent/commands/{other_command['id']}/complete", headers=headers, json={"success": True}
        )

        assert resp.status_code == 404
        still_pending = other.get("/api/agent/commands", headers=_agent_headers(other)).json()
        assert any(c["id"] == other_command["id"] for c in still_pending), (
            "the other user's command must remain untouched/pending"
        )


class TestDualModeOrganizeExisting:
    def test_with_an_agent_connected_organize_existing_is_queued(self, client):
        _connect_agent(client)
        resp = client.post("/api/organize-existing")

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is True

        commands = client.get("/api/agent/commands", headers=_agent_headers(client)).json()
        assert any(c["type"] == "organize_existing" for c in commands)


class TestDualModeOrganizePreview:
    def test_with_an_agent_connected_preview_is_queued_not_computed_locally(self, client):
        # The backend has no filesystem access to an agent-connected
        # account's real folder -- it must never invent a preview result
        # itself, only dispatch a command for the agent to compute.
        _connect_agent(client)
        resp = client.post("/api/organize/preview")

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is True
        assert body["items"] == []
        assert body["command_id"] is not None

        commands = client.get("/api/agent/commands", headers=_agent_headers(client)).json()
        assert any(c["type"] == "preview_organize_existing" for c in commands)

    def test_queuing_a_preview_creates_no_activity_log_rows(self, client, db_session):
        _connect_agent(client)

        client.post("/api/organize/preview")

        assert db_session.activity_log.count_documents({}) == 0

    def test_the_agents_reported_preview_result_is_visible_through_command_history(self, client):
        _connect_agent(client)
        client.post("/api/organize/preview")
        headers = _agent_headers(client)
        command = next(
            c for c in client.get("/api/agent/commands", headers=headers).json()
            if c["type"] == "preview_organize_existing"
        )

        resp = client.post(
            f"/api/agent/commands/{command['id']}/complete",
            headers=headers,
            json={
                "success": True,
                "result": {
                    "total": 1,
                    "ready": 1,
                    "duplicates": 0,
                    "no_match": 0,
                    "errors": 0,
                    "items": [
                        {
                            "filename": "invoice.pdf",
                            "source_path": "C:/local/invoice.pdf",
                            "destination_path": "C:/local/Finance/invoice.pdf",
                            "category": "Finance",
                            "action": "moved",
                            "status": "ready",
                            "explanation": {
                                "match_type": "keyword",
                                "matched_value": "invoice",
                                "destination": "Finance",
                                "rule_name": 'Keyword "invoice"',
                                "priority": 1,
                            },
                            "error": None,
                        }
                    ],
                },
            },
        )
        assert resp.status_code == 200

        history = client.get(
            "/api/agent-commands", params={"type": "preview_organize_existing"}
        ).json()
        assert history[0]["status"] == "done"
        assert history[0]["result"]["ready"] == 1
        assert history[0]["result"]["items"][0]["explanation"]["matched_value"] == "invoice"

    def test_completing_a_preview_command_never_touches_activity_log(self, client, db_session):
        # Confirms complete_command()'s existing type-specific branches
        # (undo/organize_existing/reclassify) correctly ignore this new
        # command type -- it must fall through to the generic status/
        # result storage only, never trigger the reclassify branch's
        # activity_log update just because a "result" dict was posted.
        _connect_agent(client)
        client.post("/api/organize/preview")
        headers = _agent_headers(client)
        command = next(
            c for c in client.get("/api/agent/commands", headers=headers).json()
            if c["type"] == "preview_organize_existing"
        )

        client.post(
            f"/api/agent/commands/{command['id']}/complete",
            headers=headers,
            json={"success": True, "result": {"total": 0, "ready": 0, "duplicates": 0, "no_match": 0, "errors": 0, "items": []}},
        )

        assert db_session.activity_log.count_documents({}) == 0

    def test_completion_result_counts_are_logged_not_silently_discarded(self, client, caplog):
        """Regression test for a real, confirmed observability gap: unlike
        reclassify (whose result.destination_path is read and applied),
        complete_command() previously accepted an organize_existing
        command's result (scanned/organized/duplicates/errors counts) in
        the request body and then never referenced it anywhere -- not
        stored, not logged. That left no trace anywhere of whether a
        remote agent's scheduled or manual "organize existing files" run
        actually did anything once it picked up the command, which is
        exactly the missing piece needed to answer "why didn't my files
        get organized" from the logs alone."""
        _connect_agent(client)
        client.post("/api/organize-existing")
        headers = _agent_headers(client)
        command = next(
            c for c in client.get("/api/agent/commands", headers=headers).json()
            if c["type"] == "organize_existing"
        )

        import logging

        with caplog.at_level(logging.INFO, logger="fileflow.agent_routes"):
            resp = client.post(
                f"/api/agent/commands/{command['id']}/complete",
                headers=headers,
                json={
                    "success": True,
                    "result": {"scanned": 3, "organized": 1, "duplicates": 0, "errors": 2},
                },
            )

        assert resp.status_code == 200
        messages = [r.message for r in caplog.records if r.name == "fileflow.agent_routes"]
        assert any(
            "scanned 3" in m and "organized 1" in m and "2 error" in m for m in messages
        ), f"expected the result counts to be logged, got: {messages}"


@pytest.fixture
def release_path(tmp_path, monkeypatch):
    """A temp path standing in for the published installer, patched into
    every module that resolves it. These tests used to write to -- and
    unlink -- the REAL backend/agent_releases/FileFlowAgentSetup-<version>.exe
    directly, so simply running the backend suite destroyed a published
    installer (found while publishing 1.0.4). The real file must never be
    touched by a test run. agent_release_sha256() is cached per-process,
    so it's cleared on both sides -- otherwise a stale hash from one
    test's fake file would leak into the next."""
    import api.agent_routes as agent_routes
    import api.routes as routes
    import config.agent_release as agent_release

    path = tmp_path / "FileFlowAgentSetup-test.exe"
    for module in (agent_release, agent_routes, routes):
        monkeypatch.setattr(module, "AGENT_RELEASE_PATH", path)
    agent_release_sha256.cache_clear()
    yield path
    agent_release_sha256.cache_clear()


@pytest.fixture
def fake_release(release_path):
    """A real (small) file at the patched installer path."""
    content = b"fake installer bytes for testing"
    release_path.write_bytes(content)
    return content


class TestDualModeUnclassifiedSuggestions:
    """Agent-connected accounts: the backend has no filesystem access of
    its own, so discovery reuses Organization Preview's existing
    "preview_organize_existing" command (no new agent command type) --
    first call queues it, a second call (once the agent's result is in)
    computes suggestions from that stored result."""

    def test_first_call_queues_the_existing_preview_command_not_a_new_one(self, client):
        _connect_agent(client)

        resp = client.post("/api/unclassified/suggestions", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is True
        assert body["command_id"] is not None
        assert body["suggestions"] == []

        commands = client.get("/api/agent/commands", headers=_agent_headers(client)).json()
        assert any(c["type"] == "preview_organize_existing" for c in commands)
        assert not any(c["type"] == "organize_existing" for c in commands)

    def test_queuing_creates_no_activity_log_rows(self, client, db_session):
        _connect_agent(client)
        client.post("/api/unclassified/suggestions", json={})
        assert db_session.activity_log.count_documents({}) == 0

    def test_a_command_still_pending_reports_still_queued(self, client):
        _connect_agent(client)
        queued = client.post("/api/unclassified/suggestions", json={}).json()

        resp = client.post(
            "/api/unclassified/suggestions", json={"command_id": queued["command_id"]}
        )

        assert resp.status_code == 200
        assert resp.json()["queued"] is True

    def test_a_completed_commands_no_match_files_get_real_suggestions(self, client, monkeypatch):
        from services import ai_unclassified_service

        monkeypatch.setattr(
            ai_unclassified_service,
            "generate_suggestion_completion",
            lambda prompt: [{"group_index": 0, "status": "unsupported", "message": "no"}],
        )
        _connect_agent(client)
        queued = client.post("/api/unclassified/suggestions", json={}).json()
        headers = _agent_headers(client)
        client.post(
            f"/api/agent/commands/{queued['command_id']}/complete",
            headers=headers,
            json={
                "success": True,
                "result": {
                    "total": 2,
                    "ready": 1,
                    "duplicates": 0,
                    "no_match": 1,
                    "errors": 0,
                    "items": [
                        {
                            "filename": "invoice.pdf",
                            "source_path": "C:/remote/invoice.pdf",
                            "destination_path": "C:/remote/Finance/invoice.pdf",
                            "category": "Finance",
                            "action": "moved",
                            "status": "ready",
                            "explanation": {
                                "match_type": "keyword",
                                "matched_value": "invoice",
                                "destination": "Finance",
                                "rule_name": 'Keyword "invoice"',
                                "priority": 1,
                            },
                            "error": None,
                        },
                        {
                            "filename": "mystery_file",
                            "source_path": "C:/remote/mystery_file",
                            "destination_path": "C:/remote/Others/mystery_file",
                            "category": "Others",
                            "action": "moved",
                            "status": "no_match",
                            "explanation": {
                                "match_type": "default",
                                "matched_value": None,
                                "destination": "Others",
                                "rule_name": None,
                                "priority": 9,
                            },
                            "error": None,
                            "file_size": 42,
                        },
                    ],
                },
            },
        )

        resp = client.post(
            "/api/unclassified/suggestions", json={"command_id": queued["command_id"]}
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is False
        assert body["total"] == 2
        assert body["unclassified"] == 1
        assert body["suggestions"][0]["file_names"] == ["mystery_file"]

    def test_never_computed_locally_when_agent_connected(self, client, monkeypatch, watch_folder):
        # Proves the backend doesn't fall back to scanning its own
        # filesystem just because a local file happens to exist -- an
        # agent-connected account's real folder is on a different machine.
        # Patches the name as bound inside ai_unclassified_service itself
        # (a `from ... import` binding, not a live alias back to
        # automation.organizer) -- the same convention used throughout this
        # codebase for a module-level single-seam function.
        calls = []
        from services import ai_unclassified_service

        monkeypatch.setattr(
            ai_unclassified_service, "plan_organize_existing", lambda *a, **k: calls.append(1)
        )
        (watch_folder / "mystery_file").write_bytes(b"data")
        _connect_agent(client)

        client.post("/api/unclassified/suggestions", json={})

        assert calls == []


class TestDualModeDuplicateAnalysis:
    """Agent-connected accounts: the backend has no filesystem access of
    its own, so this reuses the existing generic agent command mechanism
    with a new "duplicate_analysis" command type (the agent's own local
    scan can't be expressed by any existing command's shape/scope) --
    first call queues it, a second call (once the agent's result is in)
    returns that stored result directly."""

    def test_first_call_queues_a_duplicate_analysis_command(self, client):
        _connect_agent(client)

        resp = client.post("/api/duplicates/analyze", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is True
        assert body["command_id"] is not None
        assert body["groups"] == []

        commands = client.get("/api/agent/commands", headers=_agent_headers(client)).json()
        assert any(c["type"] == "duplicate_analysis" for c in commands)

    def test_queuing_creates_no_activity_log_rows(self, client, db_session):
        _connect_agent(client)
        client.post("/api/duplicates/analyze", json={})
        assert db_session.activity_log.count_documents({}) == 0

    def test_a_command_still_pending_reports_still_queued(self, client):
        _connect_agent(client)
        queued = client.post("/api/duplicates/analyze", json={}).json()

        resp = client.post("/api/duplicates/analyze", json={"command_id": queued["command_id"]})

        assert resp.status_code == 200
        assert resp.json()["queued"] is True

    def test_a_completed_commands_result_is_returned_directly(self, client):
        _connect_agent(client)
        queued = client.post("/api/duplicates/analyze", json={}).json()
        headers = _agent_headers(client)
        client.post(
            f"/api/agent/commands/{queued['command_id']}/complete",
            headers=headers,
            json={
                "success": True,
                "result": {
                    "total_files_scanned": 5,
                    "duplicate_groups": 1,
                    "duplicate_files": 2,
                    "potential_redundant_bytes": 1024,
                    "files_with_errors": 0,
                    "groups": [
                        {
                            "group_id": "abc123def456",
                            "duplicate_type": "exact_content_duplicate",
                            "file_count": 2,
                            "total_size_bytes": 2048,
                            "potential_redundant_bytes": 1024,
                            "files": [
                                {
                                    "filename": "invoice.pdf",
                                    "relative_path": "Finance/invoice.pdf",
                                    "size_bytes": 1024,
                                    "modified_at": "2026-01-10T00:00:00Z",
                                    "sha256": "a" * 64,
                                },
                                {
                                    "filename": "invoice (1).pdf",
                                    "relative_path": "Downloads/invoice (1).pdf",
                                    "size_bytes": 1024,
                                    "modified_at": "2026-01-12T00:00:00Z",
                                    "sha256": "a" * 64,
                                },
                            ],
                        }
                    ],
                    "groups_returned": 1,
                    "truncated": False,
                },
            },
        )

        resp = client.post("/api/duplicates/analyze", json={"command_id": queued["command_id"]})

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is False
        assert body["duplicate_groups"] == 1
        assert body["groups"][0]["file_count"] == 2
        assert body["groups"][0]["files"][0]["relative_path"] == "Finance/invoice.pdf"

    def test_never_computed_locally_when_agent_connected(self, client, monkeypatch, watch_folder):
        # Proves the backend doesn't fall back to scanning its own
        # filesystem just because a local file happens to exist -- an
        # agent-connected account's real folder is on a different machine.
        calls = []
        from services import duplicate_service

        monkeypatch.setattr(
            duplicate_service,
            "build_duplicate_groups_result",
            lambda *a, **k: calls.append(1),
        )
        (watch_folder / "a.bin").write_bytes(b"content")
        (watch_folder / "b.bin").write_bytes(b"content")
        _connect_agent(client)

        client.post("/api/duplicates/analyze", json={})

        assert calls == []


class TestDualModeFileSearch:
    """Agent-connected accounts: the backend has no filesystem access of
    its own, so this reuses the existing generic agent command mechanism
    with a new "file_search" command type -- the AI interpretation happens
    ONCE, on the backend, before enqueueing; the agent receives only the
    already-validated structured SearchQuery, never the natural-language
    text and never an AI provider call. A second call (once the agent's
    result is in) returns that stored result directly."""

    def _mock_ready(self, monkeypatch, query=None):
        from services import file_search_service

        monkeypatch.setattr(
            file_search_service,
            "generate_search_completion",
            lambda prompt: {"status": "ready", "query": query or {}},
        )

    def test_first_call_interprets_then_queues_a_file_search_command(self, client, monkeypatch):
        self._mock_ready(monkeypatch, {"filename_contains": ["invoice"]})
        _connect_agent(client)

        resp = client.post("/api/files/search", json={"query": "find invoices"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["queued"] is True
        assert body["command_id"] is not None
        assert any("invoice" in line.lower() for line in body["interpretation"])

        commands = client.get("/api/agent/commands", headers=_agent_headers(client)).json()
        matching = [c for c in commands if c["type"] == "file_search"]
        assert len(matching) == 1
        assert matching[0]["payload"]["query"]["filename_contains"] == ["invoice"]

    def test_the_agent_never_receives_the_natural_language_text(self, client, monkeypatch):
        self._mock_ready(monkeypatch, {"filename_contains": ["invoice"]})
        _connect_agent(client)

        client.post("/api/files/search", json={"query": "find invoices please, thanks!"})

        commands = client.get("/api/agent/commands", headers=_agent_headers(client)).json()
        payload = next(c["payload"] for c in commands if c["type"] == "file_search")
        assert "please" not in str(payload)
        assert set(payload.keys()) <= {"query", "interpretation"}

    def test_queuing_creates_no_activity_log_rows(self, client, monkeypatch, db_session):
        self._mock_ready(monkeypatch)
        _connect_agent(client)
        client.post("/api/files/search", json={"query": "find everything"})
        assert db_session.activity_log.count_documents({}) == 0

    def test_a_command_still_pending_reports_still_queued(self, client, monkeypatch):
        self._mock_ready(monkeypatch)
        _connect_agent(client)
        queued = client.post("/api/files/search", json={"query": "find everything"}).json()

        resp = client.post(
            "/api/files/search", json={"query": "find everything", "command_id": queued["command_id"]}
        )

        assert resp.status_code == 200
        assert resp.json()["queued"] is True

    def test_second_call_does_not_call_the_ai_again(self, client, monkeypatch):
        calls = []
        from services import file_search_service

        def counting(prompt):
            calls.append(prompt)
            return {"status": "ready", "query": {}}

        monkeypatch.setattr(file_search_service, "generate_search_completion", counting)
        _connect_agent(client)
        queued = client.post("/api/files/search", json={"query": "find everything"}).json()
        assert len(calls) == 1

        client.post(
            "/api/files/search", json={"query": "find everything", "command_id": queued["command_id"]}
        )

        assert len(calls) == 1  # still just the one call from the first request

    def test_a_completed_commands_result_is_returned_directly(self, client, monkeypatch):
        self._mock_ready(monkeypatch)
        _connect_agent(client)
        queued = client.post("/api/files/search", json={"query": "find everything"}).json()
        headers = _agent_headers(client)
        client.post(
            f"/api/agent/commands/{queued['command_id']}/complete",
            headers=headers,
            json={
                "success": True,
                "result": {
                    "total_files_scanned": 3,
                    "files_with_errors": 0,
                    "total_matches": 1,
                    "returned": 1,
                    "truncated": False,
                    "results": [
                        {
                            "filename": "invoice.pdf",
                            "relative_path": "Finance/invoice.pdf",
                            "extension": ".pdf",
                            "size_bytes": 1024,
                            "modified_at": "2026-08-10T00:00:00Z",
                            "category": "Finance",
                            "match_reasons": ['Filename contains "invoice"'],
                        }
                    ],
                },
            },
        )

        resp = client.post(
            "/api/files/search", json={"query": "find everything", "command_id": queued["command_id"]}
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is False
        assert body["total_matches"] == 1
        assert body["results"][0]["filename"] == "invoice.pdf"

    def test_never_computed_locally_when_agent_connected(self, client, monkeypatch, watch_folder):
        # file_search_service.py binds search_files_by_query via its own
        # `from automation.file_ops import ...` -- patch that binding (the
        # one run_file_search() actually calls), not automation.file_ops's
        # own module global.
        calls = []
        from services import file_search_service

        monkeypatch.setattr(
            file_search_service, "search_files_by_query", lambda *a, **k: calls.append(1)
        )
        self._mock_ready(monkeypatch)
        (watch_folder / "invoice.pdf").write_bytes(b"content")
        _connect_agent(client)

        client.post("/api/files/search", json={"query": "find everything"})

        assert calls == []


class TestOrganizationHealthAgentMode:
    """Agent-connected accounts: the backend has no filesystem access of
    its own, so the two filesystem-dependent Health sections (files,
    duplicates) report `status: "unavailable"` rather than the backend
    scanning a local filesystem that isn't the agent's -- pointing at the
    existing Unclassified Suggestions / Duplicate Groups features (which
    already have their own agent enqueue/poll dance) to check on demand.
    Rules and activity live in the database, not on any filesystem, so
    they're computed normally either way. Feature 8 introduces NO new
    agent command type and requires NO agent-side code changes at all --
    GET /api/health/organization never enqueues anything."""

    def test_files_and_duplicates_are_unavailable_when_agent_connected(self, client):
        _connect_agent(client)

        resp = client.get("/api/health/organization")

        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_connected"] is True
        assert body["files"]["status"] == "unavailable"
        assert body["duplicates"]["status"] == "unavailable"

    def test_rules_and_activity_remain_available_when_agent_connected(self, client, db_session):
        _connect_agent(client)
        _log(db_session, action="moved")

        body = client.get("/api/health/organization").json()

        assert body["rules"]["status"] == "available"
        assert body["rules"]["active"] == 3  # BASE_RULES
        assert body["activity"]["status"] == "available"
        assert body["activity"]["last_24_hours"]["organized"] == 1

    def test_does_not_scan_a_local_file_that_happens_to_exist(self, client, watch_folder):
        # Proves the backend doesn't fall back to its own filesystem just
        # because a same-named local folder happens to have files in it --
        # an agent-connected account's real files live on a different
        # machine, so this must stay "unavailable", never a real count.
        (watch_folder / "a.bin").write_bytes(b"content")
        (watch_folder / "b.bin").write_bytes(b"content")
        _connect_agent(client)

        body = client.get("/api/health/organization").json()

        assert body["files"]["status"] == "unavailable"
        assert body["files"]["scanned"] == 0
        assert body["duplicates"]["status"] == "unavailable"
        assert body["duplicates"]["groups"] == 0

    def test_does_not_enqueue_any_agent_command(self, client, db_session):
        _connect_agent(client)

        client.get("/api/health/organization")

        # _connect_agent() itself calls GET /api/agent/rules, which creates
        # no command -- so any command found here would mean this endpoint
        # queued one on its own, which it must never do.
        assert db_session.agent_commands.count_documents({}) == 0

class TestReleaseFixturesAreIsolated:
    """Regression: these tests used to overwrite and delete the real
    published installer at AGENT_RELEASE_PATH."""

    def test_the_fixture_path_is_never_the_real_published_installer(self, release_path):
        import api.agent_routes as agent_routes
        import api.routes as routes
        import config.agent_release as agent_release

        # AGENT_RELEASE_PATH in this module is the real, import-time path --
        # the monkeypatch only rebinds the app modules' own attributes.
        assert release_path.resolve() != AGENT_RELEASE_PATH.resolve()
        assert agent_release.AGENT_RELEASE_PATH == release_path
        assert agent_routes.AGENT_RELEASE_PATH == release_path
        assert routes.AGENT_RELEASE_PATH == release_path

    def test_serving_a_fake_release_leaves_a_real_installer_untouched(self, client, fake_release):
        real_before = AGENT_RELEASE_PATH.read_bytes() if AGENT_RELEASE_PATH.exists() else None

        resp = client.get("/api/agent/download", headers=_agent_headers(client))

        assert resp.content == fake_release  # served the temp file, not the real one
        real_after = AGENT_RELEASE_PATH.read_bytes() if AGENT_RELEASE_PATH.exists() else None
        assert real_after == real_before


class TestAgentVersion:
    def test_no_release_published_yet_is_a_404(self, client, release_path):
        assert not release_path.exists()
        resp = client.get("/api/agent/version", headers=_agent_headers(client))
        assert resp.status_code == 404

    def test_returns_the_current_version_and_matching_checksum(self, client, fake_release):
        resp = client.get("/api/agent/version", headers=_agent_headers(client))
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == AGENT_LATEST_VERSION
        assert body["sha256"] == hashlib.sha256(fake_release).hexdigest()
        assert body["download_url"] == "/api/agent/download"


class TestAgentDownload:
    def test_no_release_published_yet_is_a_404(self, client, release_path):
        assert not release_path.exists()
        resp = client.get("/api/agent/download", headers=_agent_headers(client))
        assert resp.status_code == 404

    def test_streams_the_installer_with_matching_content(self, client, fake_release):
        resp = client.get("/api/agent/download", headers=_agent_headers(client))
        assert resp.status_code == 200
        assert resp.content == fake_release
        assert hashlib.sha256(resp.content).hexdigest() == hashlib.sha256(fake_release).hexdigest()
