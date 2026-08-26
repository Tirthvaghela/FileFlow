import hashlib

import pytest

from config.agent_release import AGENT_LATEST_VERSION, AGENT_RELEASE_PATH, agent_release_sha256
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


class TestDualModeOrganizeExisting:
    def test_with_an_agent_connected_organize_existing_is_queued(self, client):
        _connect_agent(client)
        resp = client.post("/api/organize-existing")

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is True

        commands = client.get("/api/agent/commands", headers=_agent_headers(client)).json()
        assert any(c["type"] == "organize_existing" for c in commands)

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
def fake_release():
    """Creates a real (small) file at the exact path config.agent_release
    expects the published installer to live at, and cleans it up
    afterward. agent_release_sha256() is cached per-process, so it's
    cleared here too -- otherwise a stale hash from a previous test's
    fake file would leak into this one."""
    AGENT_RELEASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = b"fake installer bytes for testing"
    AGENT_RELEASE_PATH.write_bytes(content)
    agent_release_sha256.cache_clear()
    yield content
    AGENT_RELEASE_PATH.unlink(missing_ok=True)
    agent_release_sha256.cache_clear()


class TestAgentVersion:
    def test_no_release_published_yet_is_a_404(self, client):
        AGENT_RELEASE_PATH.unlink(missing_ok=True)
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
    def test_no_release_published_yet_is_a_404(self, client):
        AGENT_RELEASE_PATH.unlink(missing_ok=True)
        resp = client.get("/api/agent/download", headers=_agent_headers(client))
        assert resp.status_code == 404

    def test_streams_the_installer_with_matching_content(self, client, fake_release):
        resp = client.get("/api/agent/download", headers=_agent_headers(client))
        assert resp.status_code == 200
        assert resp.content == fake_release
        assert hashlib.sha256(resp.content).hexdigest() == hashlib.sha256(fake_release).hexdigest()
