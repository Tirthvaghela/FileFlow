from fastapi.testclient import TestClient

from main import app


class TestRegister:
    def test_creates_a_user_and_sets_a_session_cookie(self, anon_client):
        resp = anon_client.post(
            "/api/auth/register", json={"email": "new@example.com", "password": "supersecret1"}
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "new@example.com"
        assert "password" not in body
        assert "password_hash" not in body
        assert "fileflow_session" in resp.cookies
        # A brand-new account hasn't seen the setup wizard yet.
        assert body["onboarding_completed"] is False

    def test_rejects_a_duplicate_email(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "dup@example.com", "password": "supersecret1"}
        )
        resp = anon_client.post(
            "/api/auth/register", json={"email": "dup@example.com", "password": "different1"}
        )

        assert resp.status_code == 400

    def test_rejects_a_password_under_eight_characters(self, anon_client):
        resp = anon_client.post(
            "/api/auth/register", json={"email": "short@example.com", "password": "abc123"}
        )

        assert resp.status_code == 422

    def test_rejects_a_password_that_exceeds_bcrypts_72_byte_limit(self, anon_client):
        # 90 plain ASCII characters -- well under the 128-character schema
        # bound, but past bcrypt's 72-*byte* limit, which is the thing that
        # actually matters (silent truncation otherwise).
        resp = anon_client.post(
            "/api/auth/register",
            json={"email": "longpw@example.com", "password": "a" * 90},
        )

        assert resp.status_code == 422

    def test_rejects_a_password_that_exceeds_72_bytes_via_multibyte_characters(self, anon_client):
        # 71 emoji is well under the 128-character limit but each one is
        # multiple UTF-8 bytes, so this is comfortably past 72 bytes too.
        resp = anon_client.post(
            "/api/auth/register",
            json={"email": "emoji@example.com", "password": "😀" * 71},
        )

        assert resp.status_code == 422

    def test_accepts_a_long_password_that_still_fits_the_bcrypt_byte_limit(self, anon_client):
        resp = anon_client.post(
            "/api/auth/register",
            json={"email": "exactlyfits@example.com", "password": "a" * 72},
        )

        assert resp.status_code == 201

    def test_rejects_a_malformed_email(self, anon_client):
        resp = anon_client.post(
            "/api/auth/register", json={"email": "not-an-email", "password": "supersecret1"}
        )

        assert resp.status_code == 422


class TestLogin:
    def test_succeeds_with_correct_credentials(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "logintest@example.com", "password": "correct-horse1"}
        )
        # a fresh client with no cookie carried over from register
        fresh = TestClient(app)
        resp = fresh.post(
            "/api/auth/login",
            json={"email": "logintest@example.com", "password": "correct-horse1"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["requires_2fa"] is False
        assert body["user"]["email"] == "logintest@example.com"
        assert "fileflow_session" in resp.cookies

    def test_fails_with_the_wrong_password(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "wrongpw@example.com", "password": "correct-horse1"}
        )
        resp = anon_client.post(
            "/api/auth/login", json={"email": "wrongpw@example.com", "password": "incorrect1"}
        )

        assert resp.status_code == 401

    def test_fails_for_an_email_that_was_never_registered(self, anon_client):
        resp = anon_client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "whatever1"}
        )

        assert resp.status_code == 401


class TestMe:
    def test_returns_the_current_user_when_authenticated(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "me@example.com", "password": "supersecret1"}
        )

        resp = anon_client.get("/api/auth/me")

        assert resp.status_code == 200
        assert resp.json()["email"] == "me@example.com"

    def test_returns_401_with_no_session(self, anon_client):
        resp = anon_client.get("/api/auth/me")

        assert resp.status_code == 401

    def test_returns_401_for_a_garbage_cookie(self, anon_client):
        anon_client.cookies.set("fileflow_session", "not-a-real-token")

        resp = anon_client.get("/api/auth/me")

        assert resp.status_code == 401


class TestLogout:
    def test_clears_the_session_so_the_next_request_is_unauthenticated(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "logout@example.com", "password": "supersecret1"}
        )
        assert anon_client.get("/api/auth/me").status_code == 200

        logout_resp = anon_client.post("/api/auth/logout")
        assert logout_resp.status_code == 200

        assert anon_client.get("/api/auth/me").status_code == 401


class TestExistingRoutesRequireAuth:
    def test_stats_rejects_a_request_with_no_session(self, anon_client):
        resp = anon_client.get("/api/stats")
        assert resp.status_code == 401

    def test_stats_succeeds_once_registered(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "protected@example.com", "password": "supersecret1"}
        )
        resp = anon_client.get("/api/stats")
        assert resp.status_code == 200

    def test_health_never_requires_a_session(self, anon_client):
        # Deliberately public -- the frontend needs it reachable pre-login.
        resp = anon_client.get("/api/health")
        assert resp.status_code == 200


class TestOnboardingComplete:
    def test_marks_the_account_onboarded_and_it_persists(self, anon_client):
        register_resp = anon_client.post(
            "/api/auth/register",
            json={"email": "wizard@example.com", "password": "supersecret1"},
        )
        assert register_resp.json()["onboarding_completed"] is False

        resp = anon_client.post("/api/auth/onboarding-complete")

        assert resp.status_code == 200
        assert resp.json()["onboarding_completed"] is True
        assert anon_client.get("/api/auth/me").json()["onboarding_completed"] is True

    def test_requires_a_session(self, anon_client):
        resp = anon_client.post("/api/auth/onboarding-complete")
        assert resp.status_code == 401


class TestAgentToken:
    def test_issues_a_token_usable_against_agent_routes(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "agent1@example.com", "password": "supersecret1"}
        )
        resp = anon_client.post("/api/auth/agent-token")
        assert resp.status_code == 200
        token = resp.json()["token"]
        assert token

        agent_resp = anon_client.get(
            "/api/agent/rules", headers={"Authorization": f"Bearer {token}"}
        )
        assert agent_resp.status_code == 200

    def test_defaults_to_full_scope(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "agentscope1@example.com", "password": "supersecret1"}
        )
        resp = anon_client.post("/api/auth/agent-token")
        assert resp.json()["scope"] == "full"

    def test_rejects_an_unknown_scope(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "agentscope2@example.com", "password": "supersecret1"}
        )
        resp = anon_client.post("/api/auth/agent-token", json={"scope": "super-admin"})
        assert resp.status_code == 422

    def test_requires_a_session(self, anon_client):
        resp = anon_client.post("/api/auth/agent-token")
        assert resp.status_code == 401

    def test_regenerating_invalidates_the_previous_token(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "agent2@example.com", "password": "supersecret1"}
        )
        old_token = anon_client.post("/api/auth/agent-token").json()["token"]
        anon_client.post("/api/auth/agent-token")  # regenerate -- bumps the version

        resp = anon_client.get(
            "/api/agent/rules", headers={"Authorization": f"Bearer {old_token}"}
        )
        assert resp.status_code == 401

    def test_a_session_cookie_cannot_be_used_as_an_agent_token(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "agent3@example.com", "password": "supersecret1"}
        )
        session_cookie = anon_client.cookies.get("fileflow_session")

        resp = anon_client.get(
            "/api/agent/rules", headers={"Authorization": f"Bearer {session_cookie}"}
        )
        assert resp.status_code == 401

    def test_an_agent_token_cannot_be_used_as_a_session_cookie(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "agent4@example.com", "password": "supersecret1"}
        )
        agent_token = anon_client.post("/api/auth/agent-token").json()["token"]

        anon_client.cookies.set("fileflow_session", agent_token)
        resp = anon_client.get("/api/auth/me")
        assert resp.status_code == 401


class TestDeleteAccount:
    def test_requires_a_session(self, anon_client):
        resp = anon_client.request(
            "DELETE", "/api/auth/account", json={"password": "supersecret1"}
        )
        assert resp.status_code == 401

    def test_rejects_the_wrong_password(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "delwrong@example.com", "password": "supersecret1"}
        )

        resp = anon_client.request(
            "DELETE", "/api/auth/account", json={"password": "not-the-password"}
        )

        assert resp.status_code == 401
        # A wrong password must not have touched the account.
        assert anon_client.get("/api/auth/me").status_code == 200

    def test_deletes_the_account_with_the_correct_password(self, anon_client):
        anon_client.post(
            "/api/auth/register", json={"email": "delme@example.com", "password": "supersecret1"}
        )

        resp = anon_client.request(
            "DELETE", "/api/auth/account", json={"password": "supersecret1"}
        )

        assert resp.status_code == 200
        # The session is gone, not just the account -- no lingering access
        # with the same cookie the deleted account was using.
        assert anon_client.get("/api/auth/me").status_code == 401
        # The email is free again, proving the row itself is gone, not just
        # the session.
        re_register = anon_client.post(
            "/api/auth/register", json={"email": "delme@example.com", "password": "different1"}
        )
        assert re_register.status_code == 201

    def test_removes_related_activity_and_rules_data(self, anon_client, db_session):
        anon_client.post(
            "/api/auth/register", json={"email": "delcascade@example.com", "password": "supersecret1"}
        )
        user_id = anon_client.get("/api/auth/me").json()["id"]
        # str(user_id), not the bare int: RuleEngine (rules/rule_engine.py)
        # always keys a real rules document this way, never by the int id
        # directly -- inserting it with an int _id here would let this test
        # pass even if the route's own delete used the wrong type, exactly
        # the mismatch that let this cleanup silently no-op in production.
        db_session.rules.insert_one({"_id": str(user_id), "archive_folder": "Archive"})
        db_session.activity_log.insert_one({"_id": 999999, "id": 999999, "user_id": user_id})
        db_session.agent_commands.insert_one({"_id": 999999, "id": 999999, "user_id": user_id})

        resp = anon_client.request(
            "DELETE", "/api/auth/account", json={"password": "supersecret1"}
        )

        assert resp.status_code == 200
        assert db_session.rules.find_one({"_id": str(user_id)}) is None
        assert db_session.activity_log.find_one({"user_id": user_id}) is None
        assert db_session.agent_commands.find_one({"user_id": user_id}) is None
