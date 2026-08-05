import io
import json
import urllib.error
import urllib.request

import pytest

from services import email_service
from services.email_service import send_email


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture()
def resend_configured(monkeypatch):
    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(email_service.settings, "RESEND_FROM_EMAIL", "onboarding@resend.dev")


class TestSendEmail:
    def test_skips_the_request_entirely_when_no_api_key_is_set(self, monkeypatch):
        monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", None)
        calls = []
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: calls.append(a) or FakeResponse(200))

        result = send_email("Subject", "<p>hi</p>", "someone@example.com")

        assert result is False
        assert calls == []

    def test_returns_true_on_a_successful_response(self, resend_configured, monkeypatch):
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResponse(200))

        assert send_email("Subject", "<p>hi</p>", "someone@example.com") is True

    def test_sends_the_expected_payload_and_headers(self, resend_configured, monkeypatch):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return FakeResponse(200)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        send_email("Weekly digest", "<p>content</p>", "someone@example.com")

        assert captured["url"] == email_service.RESEND_API_URL
        assert captured["method"] == "POST"
        assert captured["headers"]["authorization"] == "Bearer re_test_key"
        assert captured["headers"]["content-type"] == "application/json"
        assert captured["timeout"] == 10
        assert captured["body"] == {
            "from": "onboarding@resend.dev",
            "to": ["someone@example.com"],
            "subject": "Weekly digest",
            "html": "<p>content</p>",
        }

    def test_returns_false_when_resend_rejects_the_request(self, resend_configured, monkeypatch):
        def raise_http_error(*args, **kwargs):
            raise urllib.error.HTTPError(
                url=email_service.RESEND_API_URL,
                code=401,
                msg="Unauthorized",
                hdrs=None,
                fp=io.BytesIO(b'{"message": "invalid api key"}'),
            )

        monkeypatch.setattr(urllib.request, "urlopen", raise_http_error)

        assert send_email("Subject", "<p>hi</p>", "someone@example.com") is False

    def test_returns_false_on_a_network_error(self, resend_configured, monkeypatch):
        def raise_url_error(*args, **kwargs):
            raise urllib.error.URLError("network is down")

        monkeypatch.setattr(urllib.request, "urlopen", raise_url_error)

        assert send_email("Subject", "<p>hi</p>", "someone@example.com") is False
