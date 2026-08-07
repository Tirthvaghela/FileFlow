import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_all_limiters: list["RateLimiter"] = []


class RateLimiter:
    """In-memory fixed-window limiter, keyed per caller. Good enough for
    this single-process deployment; a multi-worker/multi-instance
    deployment would need a shared store (e.g. Redis) instead.

    check() already trims each individual key's own hit-list as it expires,
    but a key that's never checked again (a one-off or long-gone caller)
    would otherwise sit in `_hits` forever -- these are public, unauthenticated
    endpoints, so sustained traffic from many distinct IPs (routine internet
    scanning, a botnet, or just a public deployment) would grow this dict
    without bound. Sweep out fully-expired keys once the dict grows past
    `max_tracked_keys`, so normal traffic never pays the sweep cost.
    """

    def __init__(self, max_requests: int, window_seconds: float, max_tracked_keys: int = 10_000):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_tracked_keys = max_tracked_keys
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()
        _all_limiters.append(self)

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            cutoff = now - self.window_seconds
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if len(hits) >= self.max_requests:
                retry_after = int(hits[0] + self.window_seconds - now) + 1
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many attempts. Try again in {retry_after}s.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

            if len(self._hits) > self.max_tracked_keys:
                self._evict_expired(cutoff)

    def _evict_expired(self, cutoff: float) -> None:
        stale_keys = [k for k, hits in self._hits.items() if not hits or hits[-1] < cutoff]
        for k in stale_keys:
            del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def reset_all() -> None:
    """Test-only: clear every limiter's state so tests stay hermetic
    regardless of execution order."""
    for limiter in _all_limiters:
        limiter.reset()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limited(limiter: RateLimiter):
    def _dependency(request: Request) -> None:
        limiter.check(client_ip(request))

    return _dependency
