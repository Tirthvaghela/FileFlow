import pyotp
from fastapi.testclient import TestClient

from main import app


def _register_and_login(anon_client, email="twofa@example.com", password="supersecret1"):
    anon_client.post("/api/auth/register", json={"email": email, "password": password})


def _enable_2fa(anon_client) -> tuple[str, list[str]]:
    """Runs the full setup->enable flow for the already-logged-in
    anon_client, returning (totp_secret, backup_codes)."""
    setup = anon_client.post("/api/auth/2fa/setup").json()
    secret = setup["secret"]
    code = pyotp.TOTP(secret).now()
    enable = anon_client.post("/api/auth/2fa/enable", json={"code": code})
    return secret, enable.json()["backup_codes"]


class TestStatus:
    def test_defaults_to_disabled(self, anon_client):
        _register_and_login(anon_client)
        resp = anon_client.get("/api/auth/2fa/status")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_requires_a_session(self, anon_client):
        resp = anon_client.get("/api/auth/2fa/status")
        assert resp.status_code == 401


class TestSetupAndEnable:
    def test_setup_returns_a_secret_and_a_qr_code(self, anon_client):
        _register_and_login(anon_client)
        resp = anon_client.post("/api/auth/2fa/setup")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["secret"]) >= 16
        assert body["qr_code_data_uri"].startswith("data:image/png;base64,")

    def test_enable_without_calling_setup_first_fails(self, anon_client):
        _register_and_login(anon_client, email="nosetup@example.com")
        resp = anon_client.post("/api/auth/2fa/enable", json={"code": "123456"})
        assert resp.status_code == 400

    def test_enable_rejects_an_incorrect_code(self, anon_client):
        _register_and_login(anon_client, email="wrongcode@example.com")
        anon_client.post("/api/auth/2fa/setup")
        resp = anon_client.post("/api/auth/2fa/enable", json={"code": "000000"})
        assert resp.status_code == 400
        assert anon_client.get("/api/auth/2fa/status").json()["enabled"] is False

    def test_enable_with_the_correct_code_turns_on_2fa_and_issues_backup_codes(self, anon_client):
        _register_and_login(anon_client, email="enableok@example.com")
        _, backup_codes = _enable_2fa(anon_client)

        assert len(backup_codes) == 8
        assert len(set(backup_codes)) == 8  # all unique
        assert anon_client.get("/api/auth/2fa/status").json()["enabled"] is True

    def test_me_reflects_totp_enabled_after_turning_it_on(self, anon_client):
        _register_and_login(anon_client, email="mecheck@example.com")
        _enable_2fa(anon_client)
        assert anon_client.get("/api/auth/me").json()["totp_enabled"] is True


class TestLoginWithTwoFactor:
    def _fresh_client(self):
        return TestClient(app)

    def test_login_requires_a_code_once_2fa_is_on(self, anon_client):
        _register_and_login(anon_client, email="loginreq@example.com")
        _enable_2fa(anon_client)

        resp = self._fresh_client().post(
            "/api/auth/login", json={"email": "loginreq@example.com", "password": "supersecret1"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["requires_2fa"] is True
        assert body["pending_token"]
        assert body["user"] is None
        assert "fileflow_session" not in resp.cookies

    def test_verify_with_the_correct_totp_code_grants_a_session(self, anon_client):
        _register_and_login(anon_client, email="verifyok@example.com")
        secret, _ = _enable_2fa(anon_client)

        login_resp = self._fresh_client().post(
            "/api/auth/login", json={"email": "verifyok@example.com", "password": "supersecret1"}
        )
        pending_token = login_resp.json()["pending_token"]

        fresh = self._fresh_client()
        verify_resp = fresh.post(
            "/api/auth/2fa/verify",
            json={"pending_token": pending_token, "code": pyotp.TOTP(secret).now()},
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["email"] == "verifyok@example.com"
        assert "fileflow_session" in verify_resp.cookies

    def test_verify_with_an_incorrect_code_fails(self, anon_client):
        _register_and_login(anon_client, email="verifybad@example.com")
        _enable_2fa(anon_client)

        login_resp = self._fresh_client().post(
            "/api/auth/login", json={"email": "verifybad@example.com", "password": "supersecret1"}
        )
        pending_token = login_resp.json()["pending_token"]

        resp = self._fresh_client().post(
            "/api/auth/2fa/verify", json={"pending_token": pending_token, "code": "000000"}
        )
        assert resp.status_code == 401

    def test_verify_with_a_bogus_pending_token_fails(self, anon_client):
        resp = self._fresh_client().post(
            "/api/auth/2fa/verify", json={"pending_token": "not-a-real-token", "code": "123456"}
        )
        assert resp.status_code == 401

    def test_a_session_cookie_cannot_be_used_as_a_pending_token(self, anon_client):
        # typ discrimination, same pattern as agent tokens -- a real
        # session cookie must never be accepted where a pending_token is
        # expected, even though both are signed with the same secret.
        _register_and_login(anon_client, email="crosstoken@example.com")
        session_cookie = anon_client.cookies.get("fileflow_session")

        resp = self._fresh_client().post(
            "/api/auth/2fa/verify", json={"pending_token": session_cookie, "code": "123456"}
        )
        assert resp.status_code == 401

    def test_verify_with_a_valid_backup_code_grants_a_session_and_consumes_it(self, anon_client):
        _register_and_login(anon_client, email="backupok@example.com")
        _, backup_codes = _enable_2fa(anon_client)

        login_resp = self._fresh_client().post(
            "/api/auth/login", json={"email": "backupok@example.com", "password": "supersecret1"}
        )
        pending_token = login_resp.json()["pending_token"]
        code = backup_codes[0]

        resp = self._fresh_client().post(
            "/api/auth/2fa/verify", json={"pending_token": pending_token, "code": code}
        )
        assert resp.status_code == 200
        assert "fileflow_session" in resp.cookies

        # The same code, and the same (now expired) pending_token, must not
        # work a second time.
        resp2 = self._fresh_client().post(
            "/api/auth/2fa/verify", json={"pending_token": pending_token, "code": code}
        )
        assert resp2.status_code == 401

    def test_login_no_longer_requires_2fa_after_it_is_disabled(self, anon_client):
        _register_and_login(anon_client, email="disableflow@example.com")
        _enable_2fa(anon_client)
        disable_resp = anon_client.post("/api/auth/2fa/disable", json={"password": "supersecret1"})
        assert disable_resp.status_code == 200

        login_resp = self._fresh_client().post(
            "/api/auth/login",
            json={"email": "disableflow@example.com", "password": "supersecret1"},
        )
        body = login_resp.json()
        assert body["requires_2fa"] is False
        assert body["user"]["email"] == "disableflow@example.com"


class TestDisable:
    def test_requires_the_correct_password(self, anon_client):
        _register_and_login(anon_client, email="disablewrong@example.com")
        _enable_2fa(anon_client)

        resp = anon_client.post("/api/auth/2fa/disable", json={"password": "not-the-password"})

        assert resp.status_code == 401
        assert anon_client.get("/api/auth/2fa/status").json()["enabled"] is True

    def test_requires_a_session(self, anon_client):
        resp = anon_client.post("/api/auth/2fa/disable", json={"password": "whatever1"})
        assert resp.status_code == 401
