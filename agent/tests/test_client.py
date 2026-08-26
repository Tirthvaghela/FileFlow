"""Automated coverage for agent/client.py -- the thin AgentClient wrapper
around the backend's /api/agent/* endpoints. No dedicated test file
existed for it before this task; every other agent test file exercises
it only through a hand-written fake client class, never the real class.

Traced against the real implementation and empirically verified (not
assumed) before writing these tests:

- Every method calls resp.raise_for_status() before touching the response
  body -- a 4xx/5xx response always raises requests.exceptions.HTTPError
  (a RequestException) before .json()/.content is ever reached, so an
  error response body can never be mistaken for valid application data.
- get_rules()/report_activity()/get_commands()/get_latest_version() all
  call resp.json() on success. In the installed requests version (2.32.3),
  requests.exceptions.JSONDecodeError is a subclass of BOTH
  requests.exceptions.RequestException AND json.JSONDecodeError/ValueError
  -- confirmed directly via the MRO, not assumed from requests' general
  reputation. That means a malformed/empty/non-JSON 2xx body already
  raises the exact exception type every caller throughout the agent
  (watcher.py, commands.py, rules_cache.py, updater.py) is built to catch
  as "backend unreachable, retry later" -- confirmed by literally
  constructing real requests.Response objects with empty, malformed, and
  HTML bodies and calling the real AgentClient methods against them.
- complete_command() never calls .json() at all -- confirmed empirically
  that a garbage response body doesn't raise anything for that method.
- reconfigure() fully replaces both base_url and the Authorization header
  (dict key assignment, not append) -- confirmed the old token is not
  present anywhere in the session's headers afterward.
- The token is only ever placed in the Authorization header, never in any
  URL -- confirmed by inspecting every URL each method actually
  constructs.
- Every method except download_installer() uses the configurable
  self.timeout (default 10.0s); download_installer() intentionally uses a
  separate, hardcoded 60.0s (tens-of-MB installer, per its own comment) --
  both confirmed directly, not merely read from the source.

This audit found no confirmed bugs in agent/client.py -- see the task's
final report for the full method-by-method breakdown. This file exists
to permanently protect the already-correct behavior traced above.
"""

import json

import pytest
import requests

from agent.client import AgentClient
from agent.config import AgentConfig


def _response(status_code=200, content: bytes = b"", json_body=None) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = json.dumps(json_body).encode() if json_body is not None else content
    return resp


class _Transport:
    """Fake replacement for session.get/session.post -- records every call
    (url + kwargs) and returns responses from a pre-set queue, one per
    call. Exercises the real AgentClient method bodies (URL construction,
    raise_for_status(), .json()/.content) -- only the actual socket/
    network layer is faked."""

    def __init__(self, *responses: requests.Response):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._responses.pop(0)


@pytest.fixture()
def client():
    config = AgentConfig(backend_url="http://backend.test", token="test-token-a", watch_folder="C:/watched")
    return AgentClient(config)


# ---------------------------------------------------------------------------
# __init__ / reconfigure
# ---------------------------------------------------------------------------


def test_init_sets_base_url_and_authorization_header(client):
    assert client.base_url == "http://backend.test"
    assert client.session.headers["Authorization"] == "Bearer test-token-a"


def test_default_timeout_is_ten_seconds(client):
    assert client.timeout == 10.0


def test_timeout_is_configurable():
    config = AgentConfig(backend_url="http://backend.test", token="t", watch_folder="C:/x")
    client = AgentClient(config, timeout=3.0)
    assert client.timeout == 3.0


def test_reconfigure_fully_replaces_base_url_and_token(client):
    new_config = AgentConfig(backend_url="http://new-backend.test", token="new-token-b", watch_folder="C:/y")

    client.reconfigure(new_config)

    assert client.base_url == "http://new-backend.test"
    assert client.session.headers["Authorization"] == "Bearer new-token-b"
    assert "test-token-a" not in str(client.session.headers), "the old token must not remain anywhere"


# ---------------------------------------------------------------------------
# Response-shape / status safety -- the core of this audit. Every case
# below was empirically confirmed against the real AgentClient before
# being written down here as a permanent regression.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method_name,call_args",
    [
        ("get_rules", ()),
        ("get_commands", ()),
        ("get_latest_version", ()),
    ],
)
def test_malformed_json_body_raises_a_request_exception_not_a_bare_value_error(client, method_name, call_args):
    client.session.get = _Transport(_response(200, content=b"{not valid json"))

    with pytest.raises(requests.exceptions.RequestException):
        getattr(client, method_name)(*call_args)


@pytest.mark.parametrize("method_name", ["get_rules", "get_commands", "get_latest_version"])
def test_empty_response_body_raises_a_request_exception(client, method_name):
    client.session.get = _Transport(_response(200, content=b""))

    with pytest.raises(requests.exceptions.RequestException):
        getattr(client, method_name)()


def test_html_error_page_with_200_status_raises_a_request_exception(client):
    """A misbehaving proxy/load balancer can return an HTML error page
    with a 200 status instead of the real backend's response. .json()
    doesn't consult Content-Type at all -- it just tries to parse the
    body -- so this must fail exactly like any other malformed JSON."""
    client.session.get = _Transport(
        _response(200, content=b"<html><body>502 Bad Gateway</body></html>")
    )

    with pytest.raises(requests.exceptions.RequestException):
        client.get_rules()


@pytest.mark.parametrize("status_code", [401, 403, 404, 409, 422, 429, 500, 502, 503, 504])
def test_error_status_codes_raise_before_the_body_is_ever_parsed(client, status_code):
    """A JSON-shaped *error* body (e.g. FastAPI's {"detail": "..."}) must
    never be returned as if it were valid application data -- confirmed
    by giving the error response a body that would parse successfully if
    .json() were ever reached, and asserting it wasn't."""
    client.session.get = _Transport(
        _response(status_code, content=b'{"detail": "some error message"}')
    )

    with pytest.raises(requests.exceptions.RequestException):
        client.get_rules()


def test_get_rules_returns_the_parsed_json_on_success(client):
    client.session.get = _Transport(_response(200, json_body={"categories": {"Documents": [".pdf"]}}))

    result = client.get_rules()

    assert result == {"categories": {"Documents": [".pdf"]}}


def test_complete_command_never_parses_the_response_body(client):
    """Traced from the source: complete_command() never calls .json() at
    all -- confirmed here that a garbage, unparseable 2xx body doesn't
    raise anything, unlike every other method in this file."""
    client.session.post = _Transport(_response(200, content=b"not json at all, garbage"))

    result = client.complete_command(1, True)

    assert result is None


def test_complete_command_still_raises_on_an_error_status(client):
    client.session.post = _Transport(_response(500, content=b'{"detail": "error"}'))

    with pytest.raises(requests.exceptions.RequestException):
        client.complete_command(1, True)


# ---------------------------------------------------------------------------
# Endpoint / URL / body construction -- confirms each method talks to the
# right endpoint, with the right HTTP method and body, and that the token
# is never placed anywhere but the Authorization header.
# ---------------------------------------------------------------------------


def test_get_rules_calls_the_correct_endpoint(client):
    transport = _Transport(_response(200, json_body={}))
    client.session.get = transport

    client.get_rules()

    assert transport.calls[0][0] == "http://backend.test/api/agent/rules"
    assert transport.calls[0][1]["timeout"] == 10.0


def test_report_activity_posts_fields_as_the_json_body(client):
    transport = _Transport(_response(200, json_body={"ok": True}))
    client.session.post = transport

    client.report_activity(original_filename="a.pdf", category="Documents")

    url, kwargs = transport.calls[0]
    assert url == "http://backend.test/api/agent/activity"
    assert kwargs["json"] == {"original_filename": "a.pdf", "category": "Documents"}


def test_get_commands_calls_the_correct_endpoint_and_returns_a_list(client):
    transport = _Transport(_response(200, json_body=[{"id": 1, "type": "undo"}]))
    client.session.get = transport

    result = client.get_commands()

    assert transport.calls[0][0] == "http://backend.test/api/agent/commands"
    assert result == [{"id": 1, "type": "undo"}]


def test_complete_command_calls_the_correct_endpoint_with_the_command_id_in_the_url(client):
    transport = _Transport(_response(200))
    client.session.post = transport

    client.complete_command(42, False, error="failed", result={"x": 1})

    url, kwargs = transport.calls[0]
    assert url == "http://backend.test/api/agent/commands/42/complete"
    assert kwargs["json"] == {"success": False, "error": "failed", "result": {"x": 1}}


def test_complete_command_defaults_result_to_an_empty_dict(client):
    transport = _Transport(_response(200))
    client.session.post = transport

    client.complete_command(1, True)

    assert transport.calls[0][1]["json"]["result"] == {}


def test_get_latest_version_calls_the_correct_endpoint(client):
    transport = _Transport(_response(200, json_body={"version": "1.0.4", "sha256": "abc"}))
    client.session.get = transport

    result = client.get_latest_version()

    assert transport.calls[0][0] == "http://backend.test/api/agent/version"
    assert result == {"version": "1.0.4", "sha256": "abc"}


def test_download_installer_calls_the_correct_endpoint_and_returns_raw_bytes(client):
    fake_installer_bytes = b"\x00\x01definitely-not-json\xff\xfe"
    transport = _Transport(_response(200, content=fake_installer_bytes))
    client.session.get = transport

    result = client.download_installer()

    assert transport.calls[0][0] == "http://backend.test/api/agent/download"
    assert result == fake_installer_bytes


def test_download_installer_uses_a_60_second_timeout_regardless_of_the_configured_default():
    config = AgentConfig(backend_url="http://backend.test", token="t", watch_folder="C:/x")
    client = AgentClient(config, timeout=2.0)  # deliberately different from 60.0
    transport = _Transport(_response(200, content=b"installer bytes"))
    client.session.get = transport

    client.download_installer()

    assert transport.calls[0][1]["timeout"] == 60.0


def test_download_installer_raises_on_an_error_status_without_returning_partial_bytes(client):
    client.session.get = _Transport(_response(404, content=b'{"detail": "No agent release published yet."}'))

    with pytest.raises(requests.exceptions.RequestException):
        client.download_installer()


def test_no_method_ever_places_the_token_in_the_url(client):
    """The token is a bearer credential -- it must only ever be sent via
    the Authorization header, never embedded in a URL (which could end up
    in server access logs, proxy logs, or browser history for anything
    that reuses this URL pattern)."""
    get_transport = _Transport(
        _response(200, json_body={}),
        _response(200, json_body=[]),
        _response(200, json_body={"version": "1.0.4", "sha256": "x"}),
        _response(200, content=b"bytes"),
    )
    post_transport = _Transport(_response(200, json_body={}), _response(200))
    client.session.get = get_transport
    client.session.post = post_transport

    client.get_rules()
    client.get_commands()
    client.get_latest_version()
    client.download_installer()
    client.report_activity(x=1)
    client.complete_command(1, True)

    for url, _kwargs in get_transport.calls + post_transport.calls:
        assert "test-token-a" not in url
