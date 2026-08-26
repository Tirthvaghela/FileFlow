import time

import pyotp
import pytest
from fastapi import HTTPException

from api.rate_limit import RateLimiter


class TestRateLimiter:
    def test_allows_requests_under_the_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.check("1.2.3.4")

    def test_blocks_once_the_limit_is_exceeded(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.check("1.2.3.4")
        limiter.check("1.2.3.4")

        with pytest.raises(HTTPException) as exc_info:
            limiter.check("1.2.3.4")

        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers

    def test_keys_are_isolated_from_each_other(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.check("1.2.3.4")
        limiter.check("5.6.7.8")

    def test_old_hits_fall_out_of_the_window(self):
        limiter = RateLimiter(max_requests=1, window_seconds=0.05)
        limiter.check("1.2.3.4")
        time.sleep(0.1)
        limiter.check("1.2.3.4")

    def test_reset_clears_all_state(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.check("1.2.3.4")
        limiter.reset()

    def test_expired_keys_are_evicted_once_the_tracked_set_grows_large(self):
        # Without eviction, a key sits in `_hits` forever even after its
        # whole hit-list has expired -- sustained traffic from many distinct
        # IPs (this limiter is applied to public, unauthenticated endpoints)
        # would grow it without bound for the life of the process.
        limiter = RateLimiter(max_requests=5, window_seconds=0.05, max_tracked_keys=3)

        for i in range(3):
            limiter.check(f"1.2.3.{i}")
        assert len(limiter._hits) == 3

        time.sleep(0.1)  # let all three keys' hits fully expire

        # Crossing max_tracked_keys on this 4th distinct key triggers a sweep.
        limiter.check("9.9.9.9")

        assert len(limiter._hits) == 1
        assert "9.9.9.9" in limiter._hits
        for i in range(3):
            assert f"1.2.3.{i}" not in limiter._hits
        limiter.check("1.2.3.4")


class TestAuthEndpointsAreRateLimited:
    def test_login_returns_429_after_too_many_attempts(self, anon_client, monkeypatch):
        from api import auth_routes

        monkeypatch.setattr(auth_routes.login_limiter, "max_requests", 3)
        anon_client.post(
            "/api/auth/register",
            json={"email": "ratelimit-login@example.com", "password": "supersecret1"},
        )

        for _ in range(3):
            resp = anon_client.post(
                "/api/auth/login",
                json={"email": "ratelimit-login@example.com", "password": "wrong-password"},
            )
            assert resp.status_code == 401

        resp = anon_client.post(
            "/api/auth/login",
            json={"email": "ratelimit-login@example.com", "password": "wrong-password"},
        )

        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_register_returns_429_after_too_many_attempts(self, anon_client, monkeypatch):
        from api import auth_routes

        monkeypatch.setattr(auth_routes.register_limiter, "max_requests", 2)

        for i in range(2):
            resp = anon_client.post(
                "/api/auth/register",
                json={"email": f"ratelimit-register-{i}@example.com", "password": "supersecret1"},
            )
            assert resp.status_code == 201

        resp = anon_client.post(
            "/api/auth/register",
            json={"email": "ratelimit-register-overflow@example.com", "password": "supersecret1"},
        )

        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_2fa_verify_returns_429_after_too_many_attempts(self, anon_client, monkeypatch):
        """Regression test for a real, confirmed gap: unlike /login,
        /register, and /forgot-password (all rate-limited above),
        POST /api/auth/2fa/verify had no rate limiting at all -- a
        pending_token (proof of a correct password only) has a 5-minute
        lifetime, and nothing bounded how many TOTP/backup-code guesses
        could be made against it within that window. The login limiter
        only throttles minting a *new* pending token, not verify attempts
        against one already obtained."""
        from api import twofa_routes

        monkeypatch.setattr(twofa_routes.verify_limiter, "max_requests", 3)

        anon_client.post(
            "/api/auth/register",
            json={"email": "ratelimit-2fa@example.com", "password": "supersecret1"},
        )
        setup = anon_client.post("/api/auth/2fa/setup").json()
        secret = setup["secret"]
        anon_client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()})

        from fastapi.testclient import TestClient
        from main import app

        login_resp = TestClient(app).post(
            "/api/auth/login",
            json={"email": "ratelimit-2fa@example.com", "password": "supersecret1"},
        )
        pending_token = login_resp.json()["pending_token"]

        for _ in range(3):
            resp = anon_client.post(
                "/api/auth/2fa/verify", json={"pending_token": pending_token, "code": "000000"}
            )
            assert resp.status_code == 401

        resp = anon_client.post(
            "/api/auth/2fa/verify", json={"pending_token": pending_token, "code": "000000"}
        )

        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
