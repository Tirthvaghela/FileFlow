"""Coverage for GET /api/agent-commands -- the browser-facing "recent
scheduled/agent activity" view added to answer, from the UI, the exact
question the scheduled-organize audit could previously only answer by
reading backend logs: did scheduled organize run, was a command queued,
did the agent complete it, and how many files did it actually organize.
"""

from fastapi.testclient import TestClient

from main import app
from services.agent_service import enqueue_agent_command

from tests.test_agent import _agent_headers, _connect_agent
from tests.test_routes import client  # noqa: F401 -- reused fixture


def _second_client(db_session, watch_folder):
    """A second, independent authenticated session against the same test
    database -- app.dependency_overrides is set on the shared `app` object
    by the `client` fixture already in effect, so a second TestClient(app)
    instance transparently reuses the same isolated db_session."""
    other = TestClient(app)
    resp = other.post(
        "/api/auth/register", json={"email": "other-user@example.com", "password": "test-password-123"}
    )
    assert resp.status_code == 201, resp.text
    other.test_user_id = resp.json()["id"]
    db_session.users.update_one(
        {"_id": other.test_user_id}, {"$set": {"watch_folder": str(watch_folder)}}
    )
    return other


class TestListAgentCommands:
    def test_authenticated_user_can_retrieve_their_own_recent_commands(self, client, db_session):
        enqueue_agent_command(db_session, client.test_user_id, "organize_existing", {"source": "scheduled"})

        resp = client.get("/api/agent-commands")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["type"] == "organize_existing"
        assert body[0]["status"] == "pending"

    def test_a_client_with_no_session_is_rejected(self, client):
        anonymous = TestClient(app)
        resp = anonymous.get("/api/agent-commands")
        assert resp.status_code in (401, 403)

    def test_user_cannot_retrieve_another_users_commands(self, client, db_session, watch_folder):
        other = _second_client(db_session, watch_folder)
        enqueue_agent_command(db_session, other.test_user_id, "organize_existing", {"source": "scheduled"})
        enqueue_agent_command(db_session, client.test_user_id, "organize_existing", {"source": "scheduled"})

        # There is no user_id (or any other ownership) query/path parameter
        # on this endpoint at all -- ownership comes only from the session
        # cookie identifying `client` vs `other`, so there is nothing a
        # malicious query string could even attempt to override.
        mine = client.get("/api/agent-commands").json()
        theirs = other.get("/api/agent-commands").json()

        assert len(mine) == 1
        assert len(theirs) == 1
        assert mine[0]["id"] != theirs[0]["id"]

    def test_results_are_ordered_newest_first(self, client, db_session):
        first = enqueue_agent_command(db_session, client.test_user_id, "organize_existing", {})
        second = enqueue_agent_command(db_session, client.test_user_id, "organize_existing", {})

        body = client.get("/api/agent-commands").json()

        assert [c["id"] for c in body] == [second["id"], first["id"]]

    def test_results_are_bounded_by_the_limit_parameter(self, client, db_session):
        for _ in range(5):
            enqueue_agent_command(db_session, client.test_user_id, "organize_existing", {})

        body = client.get("/api/agent-commands?limit=2").json()

        assert len(body) == 2

    def test_limit_is_capped_even_if_a_larger_value_is_requested(self, client, db_session):
        for _ in range(3):
            enqueue_agent_command(db_session, client.test_user_id, "organize_existing", {})

        # Mirrors GET /api/logs' own min(limit, 500) cap pattern -- this
        # endpoint caps at 100. Just confirms an oversized request doesn't
        # error and still returns real, bounded data.
        resp = client.get("/api/agent-commands?limit=99999")

        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_completed_organize_existing_exposes_its_stored_result_counts(self, client, db_session):
        _connect_agent(client)
        client.post("/api/organize-existing")
        headers = _agent_headers(client)
        command = client.get("/api/agent/commands", headers=headers).json()[0]
        client.post(
            f"/api/agent/commands/{command['id']}/complete",
            headers=headers,
            json={
                "success": True,
                "result": {"scanned": 5, "organized": 3, "duplicates": 1, "errors": 1},
            },
        )

        body = client.get("/api/agent-commands").json()

        assert len(body) == 1
        assert body[0]["status"] == "done"
        assert body[0]["success"] is True
        assert body[0]["result"] == {"scanned": 5, "organized": 3, "duplicates": 1, "errors": 1}
        assert body[0]["completed_at"] is not None

    def test_pending_command_has_no_result_or_completed_at(self, client, db_session):
        enqueue_agent_command(db_session, client.test_user_id, "organize_existing", {"source": "scheduled"})

        body = client.get("/api/agent-commands").json()

        assert body[0]["status"] == "pending"
        assert body[0]["success"] is None
        assert body[0]["result"] == {}
        assert body[0]["completed_at"] is None

    def test_failed_command_is_represented_with_success_false_and_its_error(self, client, db_session):
        _connect_agent(client)
        client.post("/api/organize-existing")
        headers = _agent_headers(client)
        command = client.get("/api/agent/commands", headers=headers).json()[0]
        client.post(
            f"/api/agent/commands/{command['id']}/complete",
            headers=headers,
            json={"success": False, "error": "disk full"},
        )

        body = client.get("/api/agent-commands").json()

        assert body[0]["status"] == "done"
        assert body[0]["success"] is False
        assert body[0]["error"] == "disk full"

    def test_response_never_contains_the_agent_token_or_authorization_header(self, client, db_session):
        headers = _agent_headers(client)
        real_token = headers["Authorization"].split(" ", 1)[1]
        _connect_agent(client)
        client.post("/api/organize-existing")

        resp = client.get("/api/agent-commands")

        assert resp.status_code == 200
        raw_body = resp.text
        assert real_token not in raw_body
        assert "Authorization" not in raw_body
        assert "payload" not in resp.json()[0]

    def test_source_filter_distinguishes_scheduled_from_manual_organize_existing(
        self, client, db_session
    ):
        """The scheduler and the manual "Organize existing files now" button
        both create type="organize_existing" commands -- payload.source is
        the only field that tells them apart (see archive_scheduler.py and
        routes.py's organize_existing route), and it is never exposed
        directly in the response, only usable as a server-side filter."""
        enqueue_agent_command(db_session, client.test_user_id, "organize_existing", {"source": "scheduled"})
        enqueue_agent_command(db_session, client.test_user_id, "organize_existing", {"source": "manual"})

        scheduled_only = client.get("/api/agent-commands?source=scheduled").json()

        assert len(scheduled_only) == 1
        assert "source" not in scheduled_only[0]
        assert "payload" not in scheduled_only[0]

    def test_type_filter_excludes_other_command_types(self, client, db_session):
        enqueue_agent_command(db_session, client.test_user_id, "organize_existing", {})
        enqueue_agent_command(db_session, client.test_user_id, "undo", {"log_id": 1})

        body = client.get("/api/agent-commands?type=organize_existing").json()

        assert len(body) == 1
        assert body[0]["type"] == "organize_existing"

    def test_response_exposes_log_id_for_undo_and_reclassify_without_the_rest_of_the_payload(
        self, client, db_session
    ):
        """History.jsx correlates a specific row with the command it
        triggered via this exact field -- added for that purpose, since
        AgentCommandHistoryOut otherwise omits payload entirely."""
        enqueue_agent_command(
            db_session, client.test_user_id, "undo",
            {"log_id": 42, "source_path": "C:/watch/a.pdf", "destination_path": "C:/watch/Documents/a.pdf"},
        )
        enqueue_agent_command(
            db_session, client.test_user_id, "reclassify",
            {"log_id": 43, "source_path": "C:/watch/Documents/b.pdf", "category": "Archive"},
        )

        body = client.get("/api/agent-commands").json()

        by_log_id = {c["log_id"]: c for c in body}
        assert set(by_log_id) == {42, 43}
        # Nothing else from payload leaks through -- source_path/
        # destination_path/category are never present on the response.
        for command in body:
            assert "source_path" not in command
            assert "destination_path" not in command
            assert "category" not in command
            assert "payload" not in command

    def test_organize_existing_has_no_log_id(self, client, db_session):
        enqueue_agent_command(db_session, client.test_user_id, "organize_existing", {"source": "manual"})

        body = client.get("/api/agent-commands").json()

        assert body[0]["log_id"] is None

    def test_log_id_filter_returns_only_the_matching_row(self, client, db_session):
        enqueue_agent_command(db_session, client.test_user_id, "undo", {"log_id": 1})
        enqueue_agent_command(db_session, client.test_user_id, "undo", {"log_id": 2})

        body = client.get("/api/agent-commands?log_id=1").json()

        assert len(body) == 1
        assert body[0]["log_id"] == 1

    def test_log_id_filter_cannot_be_used_to_reach_another_users_command(
        self, client, db_session, watch_folder
    ):
        """The same guarantee as the plain isolation test above, specifically
        against the new filter: user_id is always applied first and is never
        overridable, so filtering by another user's real log_id still
        returns nothing."""
        other = _second_client(db_session, watch_folder)
        enqueue_agent_command(db_session, other.test_user_id, "undo", {"log_id": 99})

        body = client.get("/api/agent-commands?log_id=99").json()

        assert body == []

    def test_multiple_commands_for_the_same_log_id_are_all_returned_newest_first(
        self, client, db_session
    ):
        """Confirms the raw ordering guarantee the frontend's "newest command
        wins" per-row matching relies on -- a file reclassified twice
        produces two rows for the same log_id, and the endpoint itself
        doesn't collapse them; newest-first ordering is what lets the
        frontend correctly pick the latest one."""
        first = enqueue_agent_command(db_session, client.test_user_id, "reclassify", {"log_id": 7})
        # Realistic setup for "reclassified twice": the first command must
        # actually complete before a second reclassify for the same row is
        # possible -- a partial unique index (database/db.py) now enforces
        # at most one *pending* reclassify command per log_id (a real,
        # separately-fixed concurrency bug), so two simultaneously-pending
        # commands for the same row is no longer a reachable state.
        db_session.agent_commands.update_one(
            {"_id": first["id"]}, {"$set": {"status": "done", "success": True}}
        )
        second = enqueue_agent_command(db_session, client.test_user_id, "reclassify", {"log_id": 7})

        body = client.get("/api/agent-commands?log_id=7").json()

        assert [c["id"] for c in body] == [second["id"], first["id"]]


class TestScheduledOrganizeToRecentCommandsIntegration:
    def test_scheduled_dispatch_completion_result_is_visible_through_the_recent_commands_api(
        self, client, db_session, watch_folder, test_rules, monkeypatch
    ):
        """End-to-end integration proof: a scheduled organize dispatch
        (archive_scheduler.py's own real enqueue call, source="scheduled"),
        a real agent completing it with a real result body, and the
        browser-facing recent-commands endpoint correctly surfacing that
        exact result -- the full chain this whole feature exists for."""
        from scheduler.archive_scheduler import run_scheduled_organizes
        import scheduler.archive_scheduler as archive_scheduler_module

        monkeypatch.setattr(archive_scheduler_module, "db", db_session)
        # "00:00" is the lexicographic floor of every "HH:MM" string, so the
        # scheduler's own now.strftime("%H:%M") < target_time gate always
        # passes against the real wall clock -- no need to freeze time here,
        # matching test_archive_scheduler.py's own established test_rules
        # fixture pattern rather than touching the rules collection by hand.
        test_rules["scheduled_organize_enabled"] = True
        test_rules["scheduled_organize_time"] = "00:00"
        _connect_agent(client)  # sets a real, fresh agent_last_seen_at heartbeat

        run_scheduled_organizes()

        headers = _agent_headers(client)
        pending = client.get("/api/agent/commands", headers=headers).json()
        command = next(c for c in pending if c["type"] == "organize_existing")
        client.post(
            f"/api/agent/commands/{command['id']}/complete",
            headers=headers,
            json={
                "success": True,
                "result": {"scanned": 4, "organized": 4, "duplicates": 0, "errors": 0},
            },
        )

        recent = client.get("/api/agent-commands?type=organize_existing&source=scheduled").json()

        assert len(recent) == 1
        assert recent[0]["status"] == "done"
        assert recent[0]["result"] == {"scanned": 4, "organized": 4, "duplicates": 0, "errors": 0}
