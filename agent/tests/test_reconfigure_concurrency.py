"""Deterministic coverage for the Reconfigure concurrency audit: what
happens when the tray's "Reconfigure" (main thread) mutates a live
AgentClient's base_url/token while poll_forever's background thread has a
request from that same AgentClient already in flight.

The mechanism this file proves, empirically, against the real requests
library (2.32.3) and the real AgentClient -- not assumed from documentation:

requests.sessions.Session.request() calls self.prepare_request(req)
BEFORE self.send(prep, **send_kwargs) -- prepare_request() (traced via
inspect.getsource) builds a brand new CaseInsensitiveDict copy of
self.headers via merge_setting(), and resolves the final URL, entirely
synchronously, with no network I/O involved. That copy -- not a live
reference back to session.headers -- is what every adapter and the actual
socket layer ever sees. So a request's credentials and target host are
fully decided at the moment session.get()/session.post() is called, before
any byte reaches the network, and are completely unaffected by anything
that mutates session.headers/AgentClient.base_url afterward, no matter how
long the network I/O for that request goes on to take.

The test below controls exactly when a request's network phase begins by
mounting a real requests.adapters.HTTPAdapter subclass whose send() blocks
on a threading.Event -- by the time send() is entered, prepare_request()
has unavoidably already run and handed it an already-frozen
PreparedRequest, so this gives a precise, non-sleep-based boundary to
reconfigure() around.
"""

import threading

import requests
from requests.adapters import HTTPAdapter

from agent.client import AgentClient
from agent.config import AgentConfig


class _BlockingAdapter(HTTPAdapter):
    """Real HTTPAdapter subclass standing in only for the actual socket
    layer -- everything above it (Session.request/prepare_request, and
    AgentClient's own URL-building/raise_for_status/.json()) is exercised
    for real. send() records the already-prepared request, signals
    `entered` so the test knows prepare_request() has definitely already
    run, then blocks on `release` before returning a canned response --
    letting the test perform reconfigure() at a precise point relative to
    request preparation vs. completion, with no timing guesses."""

    def __init__(self, entered: threading.Event, release: threading.Event):
        super().__init__()
        self._entered = entered
        self._release = release
        self.captured_requests: list[requests.PreparedRequest] = []

    def send(self, request, **kwargs):
        self.captured_requests.append(request)
        self._entered.set()
        self._release.wait(timeout=5)
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b'{"categories": {}}'
        resp.request = request
        return resp


def test_inflight_request_keeps_its_original_url_and_token_across_a_concurrent_reconfigure():
    """Scenario A (token rotation during GET /rules) and Scenario B
    (backend URL change during polling) collapse into the same mechanism
    for AgentClient, since every method goes through the identical
    session.get/session.post -> prepare_request -> send() path -- proven
    here once, directly, rather than assumed to generalize."""
    old_config = AgentConfig(backend_url="http://old-backend.test", token="test-token-a", watch_folder="C:/x")
    client = AgentClient(old_config)

    entered = threading.Event()
    release = threading.Event()
    adapter = _BlockingAdapter(entered, release)
    client.session.mount("http://", adapter)

    result = {}

    def _call():
        result["value"] = client.get_rules()

    t = threading.Thread(target=_call)
    t.start()
    assert entered.wait(timeout=5), "adapter.send() was never entered -- request never got that far"

    # prepare_request() has already run for this in-flight request by the
    # time send() (and therefore this wait) was reached -- its headers and
    # URL are already a frozen PreparedRequest. Reconfigure now, exactly
    # like the tray's Reconfigure would while poll_forever has a request
    # in flight.
    new_config = AgentConfig(backend_url="http://new-backend.test", token="new-token-b", watch_folder="C:/y")
    client.reconfigure(new_config)

    release.set()
    t.join(timeout=5)
    assert not t.is_alive(), "the in-flight call never completed"
    assert result["value"] == {"categories": {}}

    assert len(adapter.captured_requests) == 1
    in_flight = adapter.captured_requests[0]
    assert in_flight.headers["Authorization"] == "Bearer test-token-a", (
        "an in-flight request must keep using the token/URL it already captured "
        "before reconfigure() ran, not silently pick up a change made mid-flight"
    )
    assert in_flight.url.startswith("http://old-backend.test"), (
        "an in-flight request must stay targeted at the host it was already sent to"
    )

    # The NEXT request, made only after reconfigure() has already returned,
    # must fully use the new credentials/host -- release is already set, so
    # this second send() doesn't block.
    client.get_rules()

    assert len(adapter.captured_requests) == 2
    next_request = adapter.captured_requests[1]
    assert next_request.headers["Authorization"] == "Bearer new-token-b"
    assert next_request.url.startswith("http://new-backend.test")
    assert "test-token-a" not in next_request.headers["Authorization"], (
        "no mixing of old and new credentials on the request that follows reconfigure()"
    )
