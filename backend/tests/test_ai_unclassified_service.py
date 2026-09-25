import json
from pathlib import Path

import pytest

from config.settings import settings
from services import ai_provider, ai_unclassified_service
from services.ai_unclassified_service import (
    generate_unclassified_suggestions,
    group_unclassified_files,
)


def _write(path: Path, content: str = "x") -> Path:
    path.write_text(content)
    return path


def _mock_suggestions(monkeypatch, payload, error=None):
    def _fake(prompt):
        if error is not None:
            raise error
        return payload

    monkeypatch.setattr(ai_unclassified_service, "generate_suggestion_completion", _fake)
    return _fake


def _mock_suggestions_by_filename(monkeypatch, response_by_filename):
    """Correlates each mocked response by the representative filename the
    real prompt actually carries, rather than a hardcoded group_index --
    watch_root.iterdir() order (and therefore which group ends up at which
    index) is filesystem-dependent, not the order files were written in.
    `response_by_filename[filename]` may be a dict (a normal response,
    "group_index" filled in automatically), the string "MALFORMED" (not
    even a dict, simulating a garbled entry), or omitted entirely
    (simulating a missing entry for that group)."""

    def _fake(prompt):
        groups = json.loads(prompt)
        results = []
        for g in groups:
            entry = response_by_filename.get(g["filename"])
            if entry is None:
                continue
            if entry == "MALFORMED":
                results.append("not even a dict")
                continue
            results.append({**entry, "group_index": g["group_index"]})
        return results

    monkeypatch.setattr(ai_unclassified_service, "generate_suggestion_completion", _fake)


@pytest.fixture()
def unclassifiable_rules(test_rules):
    """conftest.py's BASE_RULES seed auto-classifies almost anything --
    `categories` maps .pdf/.txt/.jpg/.png to a real category (match_type
    "category", priority 7) and unknown extensions get auto-organized into
    their own "EXT Files" folder by default (match_type "auto_extension",
    priority 8). Neither is what these tests want: they need a file to
    genuinely fall all the way through to classify_file_explained()'s real
    match_type == "default" -- the one true "no rule matched" state this
    feature is built on (see services/ai_unclassified_service.py's own
    module docstring). keyword_rules ("invoice" -> "Finance Folder") is
    deliberately left intact so tests can still prove a real rule match is
    correctly excluded from "unclassified"."""
    test_rules["categories"] = {}
    test_rules["auto_organize_unknown_extensions"] = False
    return test_rules


class TestGroupUnclassifiedFiles:
    def test_groups_files_sharing_a_prefix_and_trailing_number(self):
        items = [
            {"filename": "receipt_1.pdf", "file_size": 100},
            {"filename": "receipt_2.pdf", "file_size": 200},
            {"filename": "receipt_3.pdf", "file_size": 300},
        ]

        groups, batch_limited = group_unclassified_files(items, max_groups=15)

        assert len(groups) == 1
        assert groups[0]["files_affected"] == 3
        assert set(groups[0]["file_names"]) == {"receipt_1.pdf", "receipt_2.pdf", "receipt_3.pdf"}
        assert batch_limited is False

    def test_does_not_group_unrelated_files(self):
        items = [
            {"filename": "receipt_1.pdf", "file_size": 100},
            {"filename": "resume_tirth.pdf", "file_size": 200},
            {"filename": "photo.jpg", "file_size": 300},
        ]

        groups, _ = group_unclassified_files(items, max_groups=15)

        assert len(groups) == 3
        assert all(g["files_affected"] == 1 for g in groups)

    def test_different_extensions_are_not_grouped_together(self):
        items = [
            {"filename": "report.pdf", "file_size": 100},
            {"filename": "report.docx", "file_size": 200},
        ]

        groups, _ = group_unclassified_files(items, max_groups=15)

        assert len(groups) == 2

    def test_batch_limited_flag_set_when_more_groups_than_the_cap(self):
        # Five genuinely unrelated stems -- unlike "unique_0.dat".."unique_4.dat",
        # which the trailing-number stripping above would correctly collapse
        # into a single group, defeating the point of this test.
        stems = ["alpha", "bravo", "charlie", "delta", "echo"]
        items = [{"filename": f"{s}.dat", "file_size": 10} for s in stems]

        groups, batch_limited = group_unclassified_files(items, max_groups=3)

        assert len(groups) == 3
        assert batch_limited is True


class TestDetectsUnclassifiedCorrectly:
    def test_only_true_default_no_match_files_get_suggestions(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        # "invoice_march.pdf" matches the seeded keyword rule ("invoice" ->
        # "Finance Folder") -- it must never be treated as unclassified.
        _write(watch_folder / "invoice_march.pdf")
        _write(watch_folder / "mystery_file.xyz")
        called = []
        monkeypatch.setattr(
            ai_unclassified_service,
            "generate_suggestion_completion",
            lambda prompt: called.append(prompt) or [
                {"group_index": 0, "status": "unsupported", "message": "no"}
            ],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.total == 2
        assert result.unclassified == 1
        assert len(result.suggestions) == 1
        assert result.suggestions[0].file_names == ["mystery_file.xyz"]

    def test_a_rule_match_produces_zero_suggestions_even_when_present(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "invoice_march.pdf")
        called = []
        monkeypatch.setattr(
            ai_unclassified_service,
            "generate_suggestion_completion",
            lambda prompt: called.append(prompt) or [],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.unclassified == 0
        assert result.suggestions == []
        assert called == []  # the AI is never even called when nothing is unclassified


class TestPrivacyOfMetadataSent:
    def test_only_safe_metadata_is_sent_to_the_ai_service(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz", "some secret content here")
        captured = {}

        def _fake(prompt):
            captured["prompt"] = prompt
            return [{"group_index": 0, "status": "unsupported", "message": "no"}]

        monkeypatch.setattr(ai_unclassified_service, "generate_suggestion_completion", _fake)

        generate_unclassified_suggestions(db_session, test_user, None)

        payload = json.loads(captured["prompt"])
        assert payload == [
            {
                "group_index": 0,
                "filename": "mystery_file.xyz",
                "extension": ".xyz",
                "size_bytes": len("some secret content here"),
                "files_affected": 1,
            }
        ]

    def test_absolute_filesystem_path_is_never_sent(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        captured = {}
        monkeypatch.setattr(
            ai_unclassified_service,
            "generate_suggestion_completion",
            lambda prompt: captured.setdefault("prompt", prompt)
            and [{"group_index": 0, "status": "unsupported", "message": "no"}],
        )

        generate_unclassified_suggestions(db_session, test_user, None)

        assert str(watch_folder) not in captured["prompt"]
        assert "source_path" not in captured["prompt"]
        assert "destination_path" not in captured["prompt"]

    def test_file_content_is_never_read_or_sent(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        secret_marker = "TOP_SECRET_MARKER_VALUE"
        _write(watch_folder / "mystery_file.xyz", secret_marker)
        captured = {}
        monkeypatch.setattr(
            ai_unclassified_service,
            "generate_suggestion_completion",
            lambda prompt: captured.setdefault("prompt", prompt)
            and [{"group_index": 0, "status": "unsupported", "message": "no"}],
        )

        generate_unclassified_suggestions(db_session, test_user, None)

        assert secret_marker not in captured["prompt"]


class TestReadyAndInvalidSuggestions:
    def test_valid_ai_suggestion_produces_structured_output(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "receipt_gst.pdf")
        _mock_suggestions(
            monkeypatch,
            [
                {
                    "group_index": 0,
                    "status": "ready",
                    "suggested_category": "Invoices",
                    "reason": ['Filename contains "invoice"', "PDF document"],
                    "suggested_rule": {
                        "rule_type": "keyword",
                        "keyword": "invoice",
                        "destination": "Finance/GSTInvoices",
                    },
                }
            ],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        s = result.suggestions[0]
        assert s.suggestion_status == "ready"
        assert s.suggested_category == "Invoices"
        assert s.suggested_destination == "Finance/GSTInvoices"
        assert s.reason == ['Filename contains "invoice"', "PDF document"]
        assert s.suggested_rule.rule_type == "keyword"
        assert s.suggested_rule.keyword == "invoice"

    def test_suggested_destination_outside_the_watch_folder_is_rejected(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        _mock_suggestions(
            monkeypatch,
            [
                {
                    "group_index": 0,
                    "status": "ready",
                    "suggested_category": "Escape",
                    "suggested_rule": {
                        "rule_type": "keyword",
                        "keyword": "mystery",
                        "destination": "../../escape",
                    },
                }
            ],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.suggestions[0].suggestion_status == "invalid"
        assert result.suggestions[0].suggested_rule is None

    def test_suggested_rule_goes_through_the_real_regexrule_redos_validation(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        _mock_suggestions(
            monkeypatch,
            [
                {
                    "group_index": 0,
                    "status": "ready",
                    "suggested_category": "Weird",
                    "suggested_rule": {
                        "rule_type": "regex",
                        "pattern": "(a+)+$",
                        "destination": "Weird",
                    },
                }
            ],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.suggestions[0].suggestion_status == "invalid"
        assert result.suggestions[0].suggested_rule is None

    def test_missing_required_rule_field_is_rejected(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        _mock_suggestions(
            monkeypatch,
            [
                {
                    "group_index": 0,
                    "status": "ready",
                    "suggested_category": "Mystery",
                    "suggested_rule": {"rule_type": "keyword", "destination": "Somewhere"},
                }
            ],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.suggestions[0].suggestion_status == "invalid"

    def test_unexpected_extra_fields_cannot_bypass_validation(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        _mock_suggestions(
            monkeypatch,
            [
                {
                    "group_index": 0,
                    "status": "ready",
                    "suggested_category": "Mystery",
                    "suggested_rule": {
                        "rule_type": "keyword",
                        "keyword": "mystery",
                        "destination": "Mystery",
                        "shell": "rm -rf /",
                        "mongo_query": {"$where": "1==1"},
                    },
                }
            ],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        s = result.suggestions[0]
        assert s.suggestion_status == "ready"
        assert "shell" not in s.suggested_rule.model_dump()
        assert "mongo_query" not in s.suggested_rule.model_dump()


class TestUnsupportedAndClarification:
    def test_unsupported_suggestion_is_handled(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        _mock_suggestions(
            monkeypatch,
            [{"group_index": 0, "status": "unsupported", "message": "No rule type fits this."}],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.suggestions[0].suggestion_status == "unsupported"
        assert result.suggestions[0].suggested_rule is None

    def test_needs_clarification_suggestion_is_handled(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        _mock_suggestions(
            monkeypatch,
            [{"group_index": 0, "status": "needs_clarification", "message": "Not enough info."}],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.suggestions[0].suggestion_status == "needs_clarification"
        assert result.suggestions[0].suggested_rule is None

    def test_low_confidence_suggestion_still_carries_reasoning(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        _mock_suggestions(
            monkeypatch,
            [
                {
                    "group_index": 0,
                    "status": "low_confidence",
                    "suggested_category": "Maybe a log file",
                    "reason": ["Extension is uncommon"],
                    "suggested_rule": {
                        "rule_type": "extension",
                        "keyword": ".xyz",
                        "destination": "Others/Unsorted",
                    },
                }
            ],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.suggestions[0].suggestion_status == "low_confidence"
        assert result.suggestions[0].reason == ["Extension is uncommon"]


class TestProviderFailureHandling:
    def test_provider_unavailable_does_not_crash_and_reports_cleanly(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        _mock_suggestions(monkeypatch, None, error=ai_provider.AIProviderUnavailable("down"))

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.suggestions == []
        assert result.unclassified == 1
        assert "unavailable" in result.message.lower()

    def test_provider_timeout_is_handled(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        _mock_suggestions(monkeypatch, None, error=ai_provider.AIProviderUnavailable("timed out"))

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.message is not None
        assert result.suggestions == []

    def test_provider_rate_limit_is_handled(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        _mock_suggestions(monkeypatch, None, error=ai_provider.AIProviderRateLimited("slow down"))

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.message is not None
        assert result.suggestions == []

    def test_malformed_top_level_response_is_rejected_without_crashing(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        # generate_suggestion_completion() itself already guarantees a list
        # (ai_provider.py raises AIProviderMalformedResponse otherwise) --
        # this simulates that guarantee firing.
        _mock_suggestions(
            monkeypatch, None, error=ai_provider.AIProviderMalformedResponse("not a JSON array")
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.message is not None
        assert result.suggestions == []


class TestPartialBatchFailure:
    def test_one_malformed_group_entry_does_not_abort_the_others(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "receipt_gst.pdf")
        _write(watch_folder / "photo.jpg")
        _mock_suggestions_by_filename(
            monkeypatch,
            {
                "receipt_gst.pdf": {
                    "status": "ready",
                    "suggested_category": "Invoices",
                    "suggested_rule": {
                        "rule_type": "keyword",
                        "keyword": "invoice",
                        "destination": "Finance",
                    },
                },
                "photo.jpg": "MALFORMED",
            },
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        statuses = {tuple(s.file_names): s.suggestion_status for s in result.suggestions}
        assert statuses[("receipt_gst.pdf",)] == "ready"
        assert statuses[("photo.jpg",)] == "unavailable"

    def test_missing_group_entry_for_one_group_does_not_abort_the_others(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "receipt_gst.pdf")
        _write(watch_folder / "photo.jpg")
        # Only group_index 0 answered -- group 1 simply missing from the array.
        _mock_suggestions(
            monkeypatch,
            [
                {
                    "group_index": 0,
                    "status": "ready",
                    "suggested_category": "Invoices",
                    "suggested_rule": {
                        "rule_type": "keyword",
                        "keyword": "invoice",
                        "destination": "Finance",
                    },
                }
            ],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert len(result.suggestions) == 2
        assert any(s.suggestion_status == "unavailable" for s in result.suggestions)
        assert any(s.suggestion_status == "ready" for s in result.suggestions)


class TestMultipleIndependentResults:
    def test_multiple_unclassified_groups_each_get_their_own_correct_result(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "receipt_gst.pdf")
        _write(watch_folder / "photo_holiday.jpg")
        _mock_suggestions_by_filename(
            monkeypatch,
            {
                "receipt_gst.pdf": {
                    "status": "ready",
                    "suggested_category": "Invoices",
                    "suggested_rule": {
                        "rule_type": "keyword",
                        "keyword": "invoice",
                        "destination": "Finance",
                    },
                },
                "photo_holiday.jpg": {
                    "status": "ready",
                    "suggested_category": "Photos",
                    "suggested_rule": {
                        "rule_type": "extension",
                        "keyword": ".jpg",
                        "destination": "Images",
                    },
                },
            },
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        by_files = {tuple(s.file_names): s for s in result.suggestions}
        assert by_files[("receipt_gst.pdf",)].suggested_destination == "Finance"
        assert by_files[("photo_holiday.jpg",)].suggested_destination == "Images"


class TestGroupedRuleReuse:
    def test_one_suggested_rule_covers_every_file_in_its_group(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "receipt_1.pdf")
        _write(watch_folder / "receipt_2.pdf")
        _write(watch_folder / "receipt_3.pdf")
        _mock_suggestions(
            monkeypatch,
            [
                {
                    "group_index": 0,
                    "status": "ready",
                    "suggested_category": "Invoices",
                    "suggested_rule": {
                        "rule_type": "keyword",
                        "keyword": "invoice",
                        "destination": "Finance",
                    },
                }
            ],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert len(result.suggestions) == 1
        assert result.suggestions[0].files_affected == 3
        assert set(result.suggestions[0].file_names) == {
            "receipt_1.pdf",
            "receipt_2.pdf",
            "receipt_3.pdf",
        }


class TestBatchSizeLimit:
    def test_more_groups_than_the_configured_cap_are_truncated_and_flagged(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        monkeypatch.setattr(settings, "AI_UNCLASSIFIED_MAX_BATCH_SIZE", 2)
        # Five genuinely unrelated stems -- see the identical note in
        # TestGroupUnclassifiedFiles above.
        for stem in ["alpha", "bravo", "charlie", "delta", "echo"]:
            _write(watch_folder / f"{stem}.dat")
        _mock_suggestions(
            monkeypatch,
            [
                {"group_index": 0, "status": "unsupported", "message": "no"},
                {"group_index": 1, "status": "unsupported", "message": "no"},
            ],
        )

        result = generate_unclassified_suggestions(db_session, test_user, None)

        assert result.unclassified == 5
        assert len(result.suggestions) == 2
        assert result.batch_limited is True


class TestRepeatedRequestsAreSafe:
    def test_two_back_to_back_requests_each_succeed_independently(
        self, watch_folder, unclassifiable_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "mystery_file.xyz")
        _mock_suggestions(
            monkeypatch, [{"group_index": 0, "status": "unsupported", "message": "no"}]
        )

        first = generate_unclassified_suggestions(db_session, test_user, None)
        second = generate_unclassified_suggestions(db_session, test_user, None)

        assert first.unclassified == second.unclassified == 1


def _agent_connected_user(test_user):
    import datetime as dt

    return {**test_user, "agent_last_seen_at": dt.datetime.now(dt.timezone.utc)}


class TestAgentConnectedCommandLookup:
    def test_unknown_command_id_returns_none(self, db_session, test_user):
        result = generate_unclassified_suggestions(
            db_session, _agent_connected_user(test_user), command_id=999999
        )
        assert result is None

    def test_a_pending_command_reports_still_queued(self, db_session, test_user):
        from database.db import insert_with_id

        command = insert_with_id(
            db_session,
            "agent_commands",
            {
                "user_id": test_user["id"],
                "type": "preview_organize_existing",
                "payload": {},
                "status": "pending",
            },
        )

        result = generate_unclassified_suggestions(
            db_session, _agent_connected_user(test_user), command["id"]
        )

        assert result.queued is True
        assert result.command_id == command["id"]
        assert result.suggestions == []
