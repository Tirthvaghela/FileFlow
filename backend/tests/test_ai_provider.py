import httpx
import pytest

from config.settings import settings
from services import ai_provider


def _response(status_code, json_body=None, text=None):
    request = httpx.Request("POST", "https://example.invalid/v1/messages")
    if text is not None:
        return httpx.Response(status_code, text=text, request=request)
    return httpx.Response(status_code, json=json_body, request=request)


def _claude_response(payload_dict):
    """A minimal, real-shaped Anthropic Messages API success body wrapping
    the given (already-serialized) JSON payload as the model's text reply."""
    import json

    return _response(200, json_body={"content": [{"type": "text", "text": json.dumps(payload_dict)}]})


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    # Pinned regardless of whatever a developer's local .env actually has
    # AI_PROVIDER set to (config/settings.py loads the real .env at import
    # time) -- TestGeminiProvider below opts into "gemini" explicitly per
    # test instead.
    monkeypatch.setattr(settings, "AI_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "AI_PROVIDER_API_KEY", "test-key-do-not-leak")


class TestGenerateRuleCompletion:
    def test_returns_the_parsed_json_object_on_success(self, monkeypatch):
        monkeypatch.setattr(
            ai_provider,
            "_request_completion",
            lambda system_prompt, prompt: _claude_response({"status": "ready", "rule": {"rule_type": "keyword"}}),
        )

        result = ai_provider.generate_rule_completion("Put invoices into Finance")

        assert result == {"status": "ready", "rule": {"rule_type": "keyword"}}

    def test_missing_api_key_raises_unavailable_without_a_network_call(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_PROVIDER_API_KEY", None)
        called = []
        monkeypatch.setattr(ai_provider, "_request_completion", lambda system_prompt, prompt: called.append(1))

        with pytest.raises(ai_provider.AIProviderUnavailable):
            ai_provider.generate_rule_completion("Put invoices into Finance")

        assert called == []

    def test_timeout_raises_unavailable(self, monkeypatch):
        def _raise(system_prompt, prompt):
            raise httpx.TimeoutException("timed out")

        monkeypatch.setattr(ai_provider, "_request_completion", _raise)

        with pytest.raises(ai_provider.AIProviderUnavailable):
            ai_provider.generate_rule_completion("Put invoices into Finance")

    def test_connection_failure_raises_unavailable(self, monkeypatch):
        def _raise(system_prompt, prompt):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(ai_provider, "_request_completion", _raise)

        with pytest.raises(ai_provider.AIProviderUnavailable):
            ai_provider.generate_rule_completion("Put invoices into Finance")

    def test_401_raises_auth_error(self, monkeypatch):
        monkeypatch.setattr(
            ai_provider, "_request_completion", lambda system_prompt, prompt: _response(401, json_body={"error": "bad key"})
        )

        with pytest.raises(ai_provider.AIProviderAuthError):
            ai_provider.generate_rule_completion("Put invoices into Finance")

    def test_403_raises_auth_error(self, monkeypatch):
        monkeypatch.setattr(
            ai_provider, "_request_completion", lambda system_prompt, prompt: _response(403, json_body={"error": "forbidden"})
        )

        with pytest.raises(ai_provider.AIProviderAuthError):
            ai_provider.generate_rule_completion("Put invoices into Finance")

    def test_429_raises_rate_limited(self, monkeypatch):
        monkeypatch.setattr(
            ai_provider, "_request_completion", lambda system_prompt, prompt: _response(429, json_body={"error": "slow down"})
        )

        with pytest.raises(ai_provider.AIProviderRateLimited):
            ai_provider.generate_rule_completion("Put invoices into Finance")

    def test_5xx_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            ai_provider, "_request_completion", lambda system_prompt, prompt: _response(503, text="upstream down")
        )

        with pytest.raises(ai_provider.AIProviderUnavailable):
            ai_provider.generate_rule_completion("Put invoices into Finance")

    def test_unexpected_status_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            ai_provider, "_request_completion", lambda system_prompt, prompt: _response(418, text="teapot")
        )

        with pytest.raises(ai_provider.AIProviderUnavailable):
            ai_provider.generate_rule_completion("Put invoices into Finance")

    def test_response_missing_expected_shape_raises_malformed(self, monkeypatch):
        monkeypatch.setattr(
            ai_provider, "_request_completion", lambda system_prompt, prompt: _response(200, json_body={"unexpected": "shape"})
        )

        with pytest.raises(ai_provider.AIProviderMalformedResponse):
            ai_provider.generate_rule_completion("Put invoices into Finance")

    def test_model_text_that_is_not_json_raises_malformed(self, monkeypatch):
        monkeypatch.setattr(
            ai_provider,
            "_request_completion",
            lambda system_prompt, prompt: _response(200, json_body={"content": [{"type": "text", "text": "Sure, I can help!"}]}),
        )

        with pytest.raises(ai_provider.AIProviderMalformedResponse):
            ai_provider.generate_rule_completion("Put invoices into Finance")

    def test_model_text_that_is_a_json_array_not_object_raises_malformed(self, monkeypatch):
        monkeypatch.setattr(
            ai_provider,
            "_request_completion",
            lambda system_prompt, prompt: _response(200, json_body={"content": [{"type": "text", "text": "[1, 2, 3]"}]}),
        )

        with pytest.raises(ai_provider.AIProviderMalformedResponse):
            ai_provider.generate_rule_completion("Put invoices into Finance")

    def test_never_sends_the_api_key_anywhere_but_the_header(self, monkeypatch):
        # _request_completion is the one real network call site -- confirm
        # it's the auth header carrying the key, not query string/body,
        # where it could end up logged by an intermediary.
        captured = {}

        def _fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _claude_response({"status": "unsupported", "message": "no"})

        monkeypatch.setattr(httpx, "post", _fake_post)

        ai_provider.generate_rule_completion("Put invoices into Finance")

        assert captured["headers"]["x-api-key"] == "test-key-do-not-leak"
        assert "test-key-do-not-leak" not in captured["url"]
        assert "test-key-do-not-leak" not in str(captured["json"])


def _gemini_response(payload_dict):
    """A minimal, real-shaped Gemini generateContent success body wrapping
    the given (already-serialized) JSON payload as the model's text reply."""
    import json

    return _response(
        200,
        json_body={"candidates": [{"content": {"parts": [{"text": json.dumps(payload_dict)}]}}]},
    )


class TestGeminiProvider:
    """AI_PROVIDER="gemini" -- a second, independently-selected request/
    response shape (services.ai_provider._PROVIDERS), not a fork of the
    Anthropic path. generate_rule_completion()'s own error-handling
    (timeouts, 401/403/429/5xx, malformed JSON) is provider-agnostic and
    already covered above against the default "anthropic" provider --
    these confirm Gemini's own request building and response parsing."""

    def test_request_builder_targets_the_configured_model_and_uses_the_goog_header(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
        monkeypatch.setattr(settings, "AI_PROVIDER_MODEL", "gemini-3.6-flash")
        captured = {}

        def _fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _gemini_response({"status": "unsupported", "message": "no"})

        monkeypatch.setattr(httpx, "post", _fake_post)

        ai_provider.generate_rule_completion("Put invoices into Finance")

        assert captured["url"].endswith("/gemini-3.6-flash:generateContent")
        assert captured["headers"]["x-goog-api-key"] == "test-key-do-not-leak"
        assert "x-api-key" not in captured["headers"]
        assert "test-key-do-not-leak" not in captured["url"]

    def test_parses_a_real_shaped_gemini_response(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
        monkeypatch.setattr(
            ai_provider,
            "_request_completion",
            lambda system_prompt, prompt: _gemini_response({"status": "ready", "rule": {"rule_type": "keyword"}}),
        )

        result = ai_provider.generate_rule_completion("Put invoices into Finance")

        assert result == {"status": "ready", "rule": {"rule_type": "keyword"}}

    def test_malformed_gemini_response_raises_malformed(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
        monkeypatch.setattr(
            ai_provider, "_request_completion", lambda system_prompt, prompt: _response(200, json_body={"unexpected": "shape"})
        )

        with pytest.raises(ai_provider.AIProviderMalformedResponse):
            ai_provider.generate_rule_completion("Put invoices into Finance")

    def test_gemini_401_still_raises_auth_error(self, monkeypatch):
        # Status-code handling in generate_rule_completion() is shared by
        # both providers -- this is the one cross-provider check that isn't
        # already implied by the anthropic-path tests above, since Gemini's
        # own request builder is never reached once the provider is known.
        monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
        monkeypatch.setattr(
            ai_provider, "_request_completion", lambda system_prompt, prompt: _response(401, json_body={"error": "bad key"})
        )

        with pytest.raises(ai_provider.AIProviderAuthError):
            ai_provider.generate_rule_completion("Put invoices into Finance")
