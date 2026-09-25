from pathlib import Path

import pytest

from services import ai_provider, ai_rule_service


def _mock_completion(monkeypatch, payload, error=None):
    def _fake(prompt):
        if error is not None:
            raise error
        return payload

    monkeypatch.setattr(ai_rule_service, "generate_rule_completion", _fake)


@pytest.fixture()
def watch_root(tmp_path):
    root = tmp_path / "watch"
    root.mkdir()
    return root


class TestReadyProposal:
    def test_valid_keyword_request_produces_a_structured_proposal(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {
                "status": "ready",
                "rule": {
                    "rule_type": "keyword",
                    "name": "GST Invoices",
                    "keyword": "invoice",
                    "destination": "Finance/Invoices",
                },
            },
        )

        result = ai_rule_service.generate_rule_proposal("Put invoices into Finance/Invoices", watch_root)

        assert result.status == "ready"
        assert result.proposal.rule_type == "keyword"
        assert result.proposal.keyword == "invoice"
        assert result.proposal.destination == "Finance/Invoices"
        assert result.proposal.name == "GST Invoices"

    def test_proposal_fields_match_the_real_rule_schema_for_each_type(self, monkeypatch, watch_root):
        # regex, extension, date, large_file, content_keyword -- each must
        # come back "ready" with the field the real rule type actually uses.
        cases = [
            ("regex", {"pattern": "^IMG_\\d+"}, "pattern"),
            ("extension", {"keyword": "pdf"}, "keyword"),
            ("date", {"older_than_days": 30}, "older_than_days"),
            ("large_file", {"threshold_mb": 500}, "threshold_mb"),
            ("content_keyword", {"keyword": "GST"}, "keyword"),
        ]
        for rule_type, extra, field in cases:
            _mock_completion(
                monkeypatch,
                {
                    "status": "ready",
                    "rule": {"rule_type": rule_type, "name": "x", "destination": "Sorted", **extra},
                },
            )
            result = ai_rule_service.generate_rule_proposal("some request", watch_root)
            assert result.status == "ready", f"{rule_type}: {result.message}"
            assert getattr(result.proposal, field) is not None

    def test_extension_is_normalized_to_start_with_a_dot(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {"status": "ready", "rule": {"rule_type": "extension", "keyword": "pdf", "destination": "Documents"}},
        )

        result = ai_rule_service.generate_rule_proposal("Put PDFs into Documents", watch_root)

        assert result.status == "ready"
        assert result.proposal.keyword == ".pdf"


class TestRejectedProposals:
    def test_unsupported_request_is_rejected(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {"status": "unsupported", "message": "That's not something FileFlow can match on."},
        )

        result = ai_rule_service.generate_rule_proposal(
            "Move files based on how important they look", watch_root
        )

        assert result.status == "unsupported"
        assert result.proposal is None
        assert "not something fileflow" in result.message.lower()

    def test_ambiguous_request_returns_clarification(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {
                "status": "needs_clarification",
                "message": "I need more detail.",
                "questions": ["What counts as important?", "Where should these go?"],
            },
        )

        result = ai_rule_service.generate_rule_proposal("Put important documents somewhere safe", watch_root)

        assert result.status == "needs_clarification"
        assert result.proposal is None
        assert len(result.questions) == 2

    def test_empty_prompt_is_rejected_without_calling_the_provider(self, monkeypatch, watch_root):
        called = []
        monkeypatch.setattr(ai_rule_service, "generate_rule_completion", lambda p: called.append(p))

        result = ai_rule_service.generate_rule_proposal("   ", watch_root)

        assert result.status == "invalid"
        assert called == []

    def test_overly_long_prompt_is_rejected_without_calling_the_provider(self, monkeypatch, watch_root):
        called = []
        monkeypatch.setattr(ai_rule_service, "generate_rule_completion", lambda p: called.append(p))

        result = ai_rule_service.generate_rule_proposal("x" * 5000, watch_root)

        assert result.status == "invalid"
        assert called == []

    def test_malformed_json_shape_is_rejected(self, monkeypatch, watch_root):
        _mock_completion(monkeypatch, {"not_a_status_field": True})

        result = ai_rule_service.generate_rule_proposal("Put invoices into Finance", watch_root)

        assert result.status == "error"

    def test_ready_rule_missing_required_fields_is_rejected(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch, {"status": "ready", "rule": {"rule_type": "keyword", "destination": "Finance"}}
        )

        result = ai_rule_service.generate_rule_proposal("Put invoices into Finance", watch_root)

        assert result.status == "invalid"

    def test_empty_keyword_is_rejected(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {"status": "ready", "rule": {"rule_type": "keyword", "keyword": "   ", "destination": "Finance"}},
        )

        result = ai_rule_service.generate_rule_proposal("Put invoices into Finance", watch_root)

        assert result.status == "invalid"

    def test_missing_destination_is_rejected(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch, {"status": "ready", "rule": {"rule_type": "keyword", "keyword": "invoice"}}
        )

        result = ai_rule_service.generate_rule_proposal("Put invoices somewhere", watch_root)

        assert result.status == "invalid"
        assert "destination" in result.message.lower()

    def test_negative_large_file_threshold_is_rejected(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {
                "status": "ready",
                "rule": {"rule_type": "large_file", "threshold_mb": -5, "destination": "Large Files"},
            },
        )

        result = ai_rule_service.generate_rule_proposal("Put huge files into Large Files", watch_root)

        assert result.status == "invalid"

    def test_negative_date_threshold_is_rejected(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {"status": "ready", "rule": {"rule_type": "date", "older_than_days": -1, "destination": "Archive"}},
        )

        result = ai_rule_service.generate_rule_proposal("Archive old files", watch_root)

        assert result.status == "invalid"

    def test_invalid_extension_is_rejected(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {"status": "ready", "rule": {"rule_type": "extension", "keyword": "../../etc", "destination": "Documents"}},
        )

        result = ai_rule_service.generate_rule_proposal("Sort weird files", watch_root)

        assert result.status == "invalid"

    def test_malformed_regex_is_rejected(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {"status": "ready", "rule": {"rule_type": "regex", "pattern": "(unclosed", "destination": "Documents"}},
        )

        result = ai_rule_service.generate_rule_proposal("match files with a weird pattern", watch_root)

        assert result.status == "invalid"

    def test_redos_prone_regex_is_rejected_by_the_real_regexrule_validator(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {"status": "ready", "rule": {"rule_type": "regex", "pattern": "(a+)+$", "destination": "Documents"}},
        )

        result = ai_rule_service.generate_rule_proposal("match files ending in a bunch of a's", watch_root)

        assert result.status == "invalid"
        assert "backtracking" in result.message.lower()

    def test_unrecognized_rule_type_is_rejected_as_unsupported(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {"status": "ready", "rule": {"rule_type": "shell_command", "destination": "Documents"}},
        )

        result = ai_rule_service.generate_rule_proposal("run a script on my files", watch_root)

        assert result.status == "unsupported"

    def test_unexpected_extra_fields_on_the_rule_are_silently_dropped_not_trusted(
        self, monkeypatch, watch_root
    ):
        _mock_completion(
            monkeypatch,
            {
                "status": "ready",
                "rule": {
                    "rule_type": "keyword",
                    "keyword": "invoice",
                    "destination": "Finance",
                    "shell": "rm -rf /",
                    "mongo_query": {"$where": "1==1"},
                },
            },
        )

        result = ai_rule_service.generate_rule_proposal("Put invoices into Finance", watch_root)

        assert result.status == "ready"
        assert not hasattr(result.proposal, "shell")
        assert not hasattr(result.proposal, "mongo_query")
        assert "shell" not in result.proposal.model_dump()
        assert "mongo_query" not in result.proposal.model_dump()


class TestDestinationSafety:
    def test_destination_outside_the_watch_folder_via_traversal_is_rejected(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {
                "status": "ready",
                "rule": {"rule_type": "keyword", "keyword": "invoice", "destination": "../../escape"},
            },
        )

        result = ai_rule_service.generate_rule_proposal("Put invoices somewhere", watch_root)

        assert result.status == "invalid"
        assert "watch folder" in result.message.lower()

    def test_absolute_destination_outside_the_watch_folder_is_rejected(self, monkeypatch, watch_root, tmp_path):
        outside = tmp_path / "elsewhere"
        _mock_completion(
            monkeypatch,
            {
                "status": "ready",
                "rule": {"rule_type": "keyword", "keyword": "invoice", "destination": str(outside)},
            },
        )

        result = ai_rule_service.generate_rule_proposal("Put invoices somewhere", watch_root)

        assert result.status == "invalid"

    def test_destination_inside_the_watch_folder_is_accepted(self, monkeypatch, watch_root):
        _mock_completion(
            monkeypatch,
            {
                "status": "ready",
                "rule": {
                    "rule_type": "keyword",
                    "keyword": "invoice",
                    "destination": "Finance/Invoices",
                },
            },
        )

        result = ai_rule_service.generate_rule_proposal("Put invoices into Finance/Invoices", watch_root)

        assert result.status == "ready"


class TestProviderFailureHandling:
    def test_provider_unavailable_is_handled_gracefully(self, monkeypatch, watch_root):
        _mock_completion(monkeypatch, None, error=ai_provider.AIProviderUnavailable("down"))

        result = ai_rule_service.generate_rule_proposal("Put invoices into Finance", watch_root)

        assert result.status == "error"
        assert "temporarily unavailable" in result.message.lower()

    def test_provider_timeout_is_handled_gracefully(self, monkeypatch, watch_root):
        # ai_provider.py itself maps a timeout to AIProviderUnavailable --
        # this confirms the service layer, one level up, degrades cleanly too.
        _mock_completion(monkeypatch, None, error=ai_provider.AIProviderUnavailable("timed out"))

        result = ai_rule_service.generate_rule_proposal("Put invoices into Finance", watch_root)

        assert result.status == "error"

    def test_provider_auth_failure_never_leaks_details_to_the_caller(self, monkeypatch, watch_root):
        _mock_completion(monkeypatch, None, error=ai_provider.AIProviderAuthError("bad key: sk-secret-123"))

        result = ai_rule_service.generate_rule_proposal("Put invoices into Finance", watch_root)

        assert result.status == "error"
        assert "sk-secret-123" not in (result.message or "")
        assert "key" not in (result.message or "").lower()

    def test_provider_rate_limit_is_surfaced_as_a_friendly_error(self, monkeypatch, watch_root):
        _mock_completion(monkeypatch, None, error=ai_provider.AIProviderRateLimited("slow down"))

        result = ai_rule_service.generate_rule_proposal("Put invoices into Finance", watch_root)

        assert result.status == "error"
        assert "busy" in result.message.lower() or "try again" in result.message.lower()

    def test_malformed_provider_response_is_handled_gracefully(self, monkeypatch, watch_root):
        _mock_completion(monkeypatch, None, error=ai_provider.AIProviderMalformedResponse("not json"))

        result = ai_rule_service.generate_rule_proposal("Put invoices into Finance", watch_root)

        assert result.status == "error"
