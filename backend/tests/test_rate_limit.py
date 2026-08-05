import time

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
