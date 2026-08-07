import re
from datetime import datetime, timedelta, timezone

from api import auth_routes


def _register(anon_client, email="reset@example.com", password="original-pw1"):
    resp = anon_client.post("/api/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201
    return resp.json()


def _capture_reset_link(monkeypatch):
    """Stands in for the real emailer so tests can read the token out of
    the link instead of guessing a value secrets.token_urlsafe() produced."""
    captured = {}

    def fake_send(to_email, reset_link):
        captured["to_email"] = to_email
        captured["reset_link"] = reset_link
        return True

    monkeypatch.setattr(auth_routes, "send_password_reset_email", fake_send)
    return captured


def _extract_token(reset_link):
    return re.search(r"token=([^&]+)", reset_link).group(1)


def _request_reset_token(anon_client, monkeypatch, email):
    captured = _capture_reset_link(monkeypatch)
    anon_client.post("/api/auth/forgot-password", json={"email": email})
    return _extract_token(captured["reset_link"])


class TestForgotPassword:
    def test_sends_a_reset_link_for_a_registered_email(self, anon_client, monkeypatch):
        _register(anon_client, email="known@example.com")
        captured = _capture_reset_link(monkeypatch)

        resp = anon_client.post("/api/auth/forgot-password", json={"email": "known@example.com"})

        assert resp.status_code == 200
        assert captured["to_email"] == "known@example.com"
        assert "token=" in captured["reset_link"]
        assert captured["reset_link"].startswith(f"{auth_routes.settings.FRONTEND_URL}/reset-password")

    def test_returns_the_same_generic_message_for_an_unregistered_email(self, anon_client, monkeypatch):
        captured = _capture_reset_link(monkeypatch)

        resp = anon_client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})

        assert resp.status_code == 200
        assert resp.json()["message"] == auth_routes.FORGOT_PASSWORD_MESSAGE
        # Nothing to email -- no account exists for this address.
        assert captured == {}

    def test_registered_and_unregistered_emails_get_an_identical_response(self, anon_client, monkeypatch):
        _register(anon_client, email="registered2@example.com")
        _capture_reset_link(monkeypatch)

        registered_resp = anon_client.post(
            "/api/auth/forgot-password", json={"email": "registered2@example.com"}
        )
        unregistered_resp = anon_client.post(
            "/api/auth/forgot-password", json={"email": "neverexisted@example.com"}
        )

        assert registered_resp.status_code == unregistered_resp.status_code == 200
        assert registered_resp.json() == unregistered_resp.json()

    def test_rejects_a_malformed_email(self, anon_client):
        resp = anon_client.post("/api/auth/forgot-password", json={"email": "not-an-email"})
        assert resp.status_code == 422


class TestResetPassword:
    def test_resets_the_password_and_allows_login_with_the_new_one(self, anon_client, monkeypatch):
        _register(anon_client, email="reset1@example.com", password="original-pw1")
        token = _request_reset_token(anon_client, monkeypatch, "reset1@example.com")

        resp = anon_client.post(
            "/api/auth/reset-password", json={"token": token, "password": "brand-new-pw1"}
        )
        assert resp.status_code == 200

        old_login = anon_client.post(
            "/api/auth/login", json={"email": "reset1@example.com", "password": "original-pw1"}
        )
        assert old_login.status_code == 401

        new_login = anon_client.post(
            "/api/auth/login", json={"email": "reset1@example.com", "password": "brand-new-pw1"}
        )
        assert new_login.status_code == 200

    def test_the_token_cannot_be_reused_after_a_successful_reset(self, anon_client, monkeypatch):
        _register(anon_client, email="reset2@example.com", password="original-pw1")
        token = _request_reset_token(anon_client, monkeypatch, "reset2@example.com")

        first = anon_client.post(
            "/api/auth/reset-password", json={"token": token, "password": "brand-new-pw1"}
        )
        assert first.status_code == 200

        second = anon_client.post(
            "/api/auth/reset-password", json={"token": token, "password": "another-pw1"}
        )
        assert second.status_code == 400

    def test_rejects_an_unknown_token(self, anon_client):
        resp = anon_client.post(
            "/api/auth/reset-password",
            json={"token": "not-a-real-token", "password": "brand-new-pw1"},
        )
        assert resp.status_code == 400

    def test_rejects_an_expired_token(self, anon_client, db_session, monkeypatch):
        _register(anon_client, email="expired@example.com", password="original-pw1")
        token = _request_reset_token(anon_client, monkeypatch, "expired@example.com")

        db_session.users.update_one(
            {"email": "expired@example.com"},
            {"$set": {"reset_token_expires": datetime.now(timezone.utc) - timedelta(minutes=1)}},
        )

        resp = anon_client.post(
            "/api/auth/reset-password", json={"token": token, "password": "brand-new-pw1"}
        )
        assert resp.status_code == 400

    def test_rejects_a_password_under_eight_characters(self, anon_client, monkeypatch):
        _register(anon_client, email="shortpw@example.com", password="original-pw1")
        token = _request_reset_token(anon_client, monkeypatch, "shortpw@example.com")

        resp = anon_client.post(
            "/api/auth/reset-password", json={"token": token, "password": "short1"}
        )
        assert resp.status_code == 422

    def test_a_second_forgot_password_request_invalidates_the_first_tokens_use(
        self, anon_client, monkeypatch
    ):
        _register(anon_client, email="tworequests@example.com", password="original-pw1")
        first_token = _request_reset_token(anon_client, monkeypatch, "tworequests@example.com")
        _request_reset_token(anon_client, monkeypatch, "tworequests@example.com")

        resp = anon_client.post(
            "/api/auth/reset-password", json={"token": first_token, "password": "brand-new-pw1"}
        )
        assert resp.status_code == 400
