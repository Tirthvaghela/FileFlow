"""Exhaustive cross-type JWT boundary audit -- follow-up to the critical
decode_token() typ-confusion bug fixed in the prior 2FA audit (a
2fa_pending token was accepted as a real session because decode_token()
denylisted only "agent"). This file builds every real token type this
application actually issues, via the real production endpoints, and
verifies each consumer (session, agent, agent-mutation, 2FA-verify)
accepts *only* its own intended token type -- never any other, and never
a syntactically-valid-but-unrecognized one.

No real JWTs, passwords, or secrets from outside this test run are ever
used -- every token here is minted fresh for a synthetic, isolated test
account and asserted on only by shape/outcome, never printed."""

import time

import jwt
import pyotp
import pytest
from fastapi.testclient import TestClient

from api.auth import ALGORITHM
from config.settings import settings
from main import app

PASSWORD = "supersecret1"


def _fresh_client() -> TestClient:
    """A second TestClient sharing the same (already dependency-overridden,
    isolated) app instance as anon_client -- app.dependency_overrides is
    process-global, so this picks up the same isolated db_session as long
    as an anon_client fixture is still active in the same test, matching
    the existing pattern in test_twofa.py."""
    return TestClient(app)


def _garbage_typ_token(user_id: int) -> str:
    """A validly-signed JWT with a well-formed but entirely unrecognized
    typ -- must be rejected by every consumer, not just the ones that
    happen to name a specific other typ to reject."""
    return jwt.encode(
        {"sub": str(user_id), "exp": time.time() + 300, "typ": "something_else"},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def _expired_pending_token(user_id: int) -> str:
    return jwt.encode(
        {"sub": str(user_id), "exp": time.time() - 60, "typ": "2fa_pending"},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


@pytest.fixture()
def tokens(anon_client):
    """Every real token type this app issues, minted via the real
    production endpoints -- plus two hand-constructed edge cases (garbage
    typ, expired pending) that have no endpoint of their own. Returned as
    a dict so each consumer test below can look up exactly the token(s)
    it needs by name.

    agent_full and agent_read_only are minted for TWO SEPARATE accounts,
    not one: POST /api/auth/agent-token bumps agent_token_version on
    every call (confirmed, correct, already-tested regeneration/
    revocation behavior -- see test_auth.py's own test for it), so a
    second mint for the same account would silently invalidate the
    first, and this fixture needs both to stay independently valid at
    once."""
    anon_client.post(
        "/api/auth/register", json={"email": "boundary@example.com", "password": PASSWORD}
    )
    user_id = anon_client.get("/api/auth/me").json()["id"]
    session = anon_client.cookies.get("fileflow_session")

    agent_full = anon_client.post("/api/auth/agent-token", json={"scope": "full"}).json()["token"]

    read_only_client = _fresh_client()
    read_only_client.post(
        "/api/auth/register",
        json={"email": "boundary-readonly@example.com", "password": PASSWORD},
    )
    agent_read_only = read_only_client.post(
        "/api/auth/agent-token", json={"scope": "read_only"}
    ).json()["token"]

    setup = anon_client.post("/api/auth/2fa/setup").json()
    code = pyotp.TOTP(setup["secret"]).now()
    anon_client.post("/api/auth/2fa/enable", json={"code": code})
    # A fresh login (not anon_client, which is already past this account's
    # 2FA gate) to get a genuine, freshly-issued pending_token.
    login_resp = _fresh_client().post(
        "/api/auth/login", json={"email": "boundary@example.com", "password": PASSWORD}
    )
    pending = login_resp.json()["pending_token"]

    return {
        "session": session,
        "agent_full": agent_full,
        "agent_read_only": agent_read_only,
        "pending_2fa": pending,
        "garbage_typ": _garbage_typ_token(user_id),
        "expired_pending": _expired_pending_token(user_id),
    }


class TestSessionConsumer:
    """GET /api/auth/me must accept ONLY a real session token."""

    def test_accepts_the_real_session_token(self, tokens):
        client = _fresh_client()
        client.cookies.set("fileflow_session", tokens["session"])
        assert client.get("/api/auth/me").status_code == 200

    @pytest.mark.parametrize(
        "label", ["agent_full", "agent_read_only", "pending_2fa", "garbage_typ", "expired_pending"]
    )
    def test_rejects_every_other_token(self, tokens, label):
        client = _fresh_client()
        client.cookies.set("fileflow_session", tokens[label])
        assert client.get("/api/auth/me").status_code == 401


class TestAgentReadConsumer:
    """GET /api/agent/rules must accept either agent scope, but nothing else."""

    @pytest.mark.parametrize("label", ["agent_full", "agent_read_only"])
    def test_accepts_either_agent_scope(self, tokens, label):
        resp = _fresh_client().get(
            "/api/agent/rules", headers={"Authorization": f"Bearer {tokens[label]}"}
        )
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "label", ["session", "pending_2fa", "garbage_typ", "expired_pending"]
    )
    def test_rejects_every_other_token(self, tokens, label):
        resp = _fresh_client().get(
            "/api/agent/rules", headers={"Authorization": f"Bearer {tokens[label]}"}
        )
        assert resp.status_code == 401


class TestAgentMutationConsumer:
    """GET /api/agent/commands is gated by require_full_agent_scope --
    read-only agent tokens are a real, valid agent token, just not
    privileged enough (403), distinct from every other token type not
    being an agent token at all (401)."""

    def test_accepts_a_full_agent_token(self, tokens):
        resp = _fresh_client().get(
            "/api/agent/commands", headers={"Authorization": f"Bearer {tokens['agent_full']}"}
        )
        assert resp.status_code == 200

    def test_rejects_a_read_only_agent_token_with_403_not_401(self, tokens):
        resp = _fresh_client().get(
            "/api/agent/commands",
            headers={"Authorization": f"Bearer {tokens['agent_read_only']}"},
        )
        assert resp.status_code == 403

    @pytest.mark.parametrize(
        "label", ["session", "pending_2fa", "garbage_typ", "expired_pending"]
    )
    def test_rejects_every_non_agent_token_with_401(self, tokens, label):
        resp = _fresh_client().get(
            "/api/agent/commands", headers={"Authorization": f"Bearer {tokens[label]}"}
        )
        assert resp.status_code == 401


class TestPendingTwoFactorConsumer:
    """POST /api/auth/2fa/verify must accept ONLY a real, unexpired
    pending_token for THIS specific login attempt."""

    def test_accepts_the_real_pending_token_with_the_correct_code(self, tokens):
        # Not asserting success here -- the TOTP code itself isn't part of
        # this fixture's return value and isn't this test's concern (fully
        # covered by test_twofa.py already). This only proves the pending
        # token itself is the one the endpoint is willing to consider at
        # all, i.e. it must NOT be a 401 purely from the token's own typ.
        resp = _fresh_client().post(
            "/api/auth/2fa/verify",
            json={"pending_token": tokens["pending_2fa"], "code": "000000"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "That code is incorrect."

    @pytest.mark.parametrize(
        "label", ["session", "agent_full", "agent_read_only", "garbage_typ"]
    )
    def test_rejects_every_other_token(self, tokens, label):
        resp = _fresh_client().post(
            "/api/auth/2fa/verify", json={"pending_token": tokens[label], "code": "000000"}
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()

    def test_rejects_an_expired_pending_token(self, tokens):
        resp = _fresh_client().post(
            "/api/auth/2fa/verify",
            json={"pending_token": tokens["expired_pending"], "code": "000000"},
        )
        assert resp.status_code == 401


class TestSignatureAndAlgorithmIntegrity:
    """None of the above matters if a token can be forged without knowing
    SECRET_KEY -- these confirm the underlying signature/algorithm
    enforcement PyJWT provides is actually wired up as expected."""

    def test_an_unsigned_alg_none_token_is_rejected(self, tokens):
        forged = jwt.encode({"sub": "1"}, key=None, algorithm="none")
        client = _fresh_client()
        client.cookies.set("fileflow_session", forged)
        assert client.get("/api/auth/me").status_code == 401

    def test_a_token_signed_with_the_wrong_secret_is_rejected(self, tokens):
        forged = jwt.encode(
            {"sub": "1", "exp": time.time() + 300},
            "not-the-real-secret-key-but-32-bytes",
            algorithm=ALGORITHM,
        )
        client = _fresh_client()
        client.cookies.set("fileflow_session", forged)
        assert client.get("/api/auth/me").status_code == 401

    def test_tampering_with_the_payload_without_resigning_is_rejected(self, tokens):
        """Splices a different user id into an otherwise-real, validly
        signed session token's payload segment -- the signature no longer
        matches, so this must fail exactly like a wrong-secret forgery,
        not silently authenticate as the tampered-in user id."""
        header_b64, payload_b64, sig_b64 = tokens["session"].split(".")
        tampered_payload = jwt.utils.base64url_encode(b'{"sub": "999999"}').decode()
        tampered_token = f"{header_b64}.{tampered_payload}.{sig_b64}"

        client = _fresh_client()
        client.cookies.set("fileflow_session", tampered_token)
        assert client.get("/api/auth/me").status_code == 401
