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
        assert resp.json()["email"] == "logintest@example.com"
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
