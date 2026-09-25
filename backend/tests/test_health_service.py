"""Organization Health Dashboard: aggregation-correctness tests against
services/health_service.py directly -- each section's math against real
files/rules/activity_log rows, zero-file edge cases, and partial-failure
resilience. Route-level wiring (auth, isolation, agent mode) is covered by
tests/test_routes.py::TestOrganizationHealth and
tests/test_agent.py::TestOrganizationHealthAgentMode."""

from datetime import datetime, timedelta, timezone

import pytest

from services import health_service
from services.health_service import get_organization_health


@pytest.fixture()
def user(test_user):
    return test_user


class TestFilesSection:
    def test_zero_files_does_not_divide_by_zero(self, db_session, user, test_rules):
        result = get_organization_health(db_session, user)
        assert result.files.scanned == 0
        assert result.files.classification_coverage_percent is None

    def test_classified_and_unclassified_counts(self, db_session, user, test_rules, watch_folder):
        # auto_organize_unknown_extensions defaults True, which would
        # auto-classify "mystery.xyz" into "XYZ Files" (match_type ==
        # "auto_extension", not "default") -- disabled here so an
        # unmatched extension genuinely falls through to no_match.
        test_rules["auto_organize_unknown_extensions"] = False
        (watch_folder / "invoice_1.pdf").write_bytes(b"content")  # matches keyword_rule "invoice"
        (watch_folder / "mystery.xyz").write_bytes(b"content")  # no matching rule -> no_match

        result = get_organization_health(db_session, user)

        assert result.files.scanned == 2
        assert result.files.classified == 1
        assert result.files.unclassified == 1
        assert result.files.errors == 0
        assert result.files.classification_coverage_percent == 50.0

    def test_unclassified_matches_feature_4s_own_definition(self, db_session, user, test_rules, watch_folder):
        from automation.organizer import plan_organize_existing

        test_rules["auto_organize_unknown_extensions"] = False
        (watch_folder / "mystery.xyz").write_bytes(b"content")

        items = plan_organize_existing(db_session, user)
        no_match_count = sum(1 for i in items if i["status"] == "no_match")

        result = get_organization_health(db_session, user)

        assert result.files.unclassified == no_match_count == 1

    def test_full_coverage_when_everything_matches(self, db_session, user, test_rules, watch_folder):
        (watch_folder / "invoice_1.pdf").write_bytes(b"content")
        (watch_folder / "invoice_2.pdf").write_bytes(b"content")

        result = get_organization_health(db_session, user)

        assert result.files.classification_coverage_percent == 100.0

    def test_already_organized_subfolder_files_are_not_rescanned(self, db_session, user, test_rules, watch_folder):
        # plan_organize_existing() -- and therefore this section -- only
        # scans each watch root's top level, exactly like AI Unclassified
        # Suggestions; files FileFlow already organized into a category
        # subfolder are left alone, never re-counted here.
        (watch_folder / "Finance Folder").mkdir()
        (watch_folder / "Finance Folder" / "already_organized.pdf").write_bytes(b"content")

        result = get_organization_health(db_session, user)

        assert result.files.scanned == 0


class TestDuplicatesSection:
    def test_no_duplicates(self, db_session, user, test_rules, watch_folder):
        (watch_folder / "a.bin").write_bytes(b"unique")
        result = get_organization_health(db_session, user)
        assert result.duplicates.groups == 0
        assert result.duplicates.duplicate_files == 0
        assert result.duplicates.potential_redundant_bytes == 0

    def test_a_real_duplicate_pair(self, db_session, user, test_rules, watch_folder):
        (watch_folder / "a.bin").write_bytes(b"same content")
        (watch_folder / "b.bin").write_bytes(b"same content")

        result = get_organization_health(db_session, user)

        assert result.duplicates.groups == 1
        assert result.duplicates.duplicate_files == 2
        assert result.duplicates.potential_redundant_bytes == len(b"same content")

    def test_uses_the_real_duplicate_analyzer_not_a_second_implementation(
        self, db_session, user, test_rules, monkeypatch
    ):
        calls = []
        monkeypatch.setattr(
            health_service,
            "build_duplicate_groups_result",
            lambda *a, **k: calls.append(1) or {
                "duplicate_groups": 7,
                "duplicate_files": 14,
                "potential_redundant_bytes": 999,
            },
        )

        result = get_organization_health(db_session, user)

        assert calls == [1]
        assert result.duplicates.groups == 7
        assert result.duplicates.duplicate_files == 14
        assert result.duplicates.potential_redundant_bytes == 999


class TestRulesSection:
    def test_active_rule_count(self, db_session, user, test_rules):
        # test_rules (conftest.BASE_RULES): 1 extension_rule, 1 keyword_rule,
        # 1 enabled large_file rule -> 3 active, 0 disabled.
        result = get_organization_health(db_session, user)
        assert result.rules.active == 3
        assert result.rules.disabled == 0

    def test_disabled_rules_are_counted_separately(self, db_session, user, test_rules):
        test_rules["disabled_keyword_rules"] = [{"keyword": "old", "folder": "Archive"}]
        result = get_organization_health(db_session, user)
        assert result.rules.disabled == 1
        assert result.rules.active == 3

    def test_conflicts_come_from_the_real_conflict_detector(self, db_session, user, test_rules):
        # Two keyword rules where the earlier's keyword is a substring of
        # the later's, sending it elsewhere -- a real, provable shadow.
        test_rules["keyword_rules"] = [
            {"keyword": "invoice", "folder": "Finance"},
            {"keyword": "invoice_2024", "folder": "Archive"},
        ]

        result = get_organization_health(db_session, user)

        assert result.rules.conflicts_total >= 1
        assert result.rules.conflicts_high >= 1

    def test_redundant_rule_count(self, db_session, user, test_rules):
        test_rules["keyword_rules"] = [
            {"keyword": "invoice", "folder": "Finance"},
            {"keyword": "invoice", "folder": "Finance"},
        ]

        result = get_organization_health(db_session, user)

        assert result.rules.redundant_rules == 1

    def test_no_conflicts_when_rules_dont_overlap(self, db_session, user, test_rules):
        # BASE_RULES also carries an extension_rule and an enabled
        # large_file rule -- cleared here too, since either could
        # legitimately overlap with the keyword rule via cross-type
        # candidate evaluation (a real Feature 5 finding, not a bug).
        test_rules["keyword_rules"] = [{"keyword": "invoice", "folder": "Finance"}]
        test_rules["extension_rules"] = {}
        test_rules["large_file_enabled"] = False

        result = get_organization_health(db_session, user)

        assert result.rules.conflicts_total == 0
        assert result.rules.redundant_rules == 0


class TestActivitySection:
    def test_counts_within_each_window(self, db_session, user, log_factory):
        now = datetime.now(timezone.utc)
        log_factory(action="moved", timestamp=now - timedelta(hours=1))
        log_factory(action="moved", timestamp=now - timedelta(days=3))
        log_factory(action="moved", timestamp=now - timedelta(days=20))
        log_factory(action="moved", timestamp=now - timedelta(days=40))  # outside every window
        log_factory(action="duplicate_skipped", timestamp=now - timedelta(hours=1))

        result = get_organization_health(db_session, user)

        assert result.activity.last_24_hours.organized == 1
        assert result.activity.last_24_hours.skipped == 1
        assert result.activity.last_7_days.organized == 2
        assert result.activity.last_30_days.organized == 3

    def test_preview_operations_are_never_counted(self, db_session, user, test_rules, watch_folder):
        # plan_organize_existing() (called by the files section above) never
        # writes an activity_log row -- confirms the activity section can't
        # accidentally pick up a preview as real organization.
        (watch_folder / "invoice_1.pdf").write_bytes(b"content")

        result = get_organization_health(db_session, user)

        assert result.activity.last_24_hours.organized == 0

    def test_zero_activity_is_zero_not_missing(self, db_session, user):
        result = get_organization_health(db_session, user)
        assert result.activity.last_24_hours.organized == 0
        assert result.activity.status == "available"

    def test_only_this_accounts_activity_is_counted(self, db_session, user, log_factory):
        log_factory(action="moved", user_id=999)  # a different account
        result = get_organization_health(db_session, user)
        assert result.activity.last_30_days.organized == 0


class TestPartialFailure:
    def test_duplicate_failure_does_not_break_the_rest(self, db_session, user, test_rules, monkeypatch):
        monkeypatch.setattr(
            health_service, "build_duplicate_groups_result", lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
        )

        result = get_organization_health(db_session, user)

        assert result.duplicates.status == "unavailable"
        assert result.duplicates.message
        assert result.rules.status == "available"
        assert result.activity.status == "available"

    def test_rule_conflict_failure_is_represented_as_unavailable(self, db_session, user, test_rules, monkeypatch):
        monkeypatch.setattr(
            health_service, "analyze_conflicts", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom"))
        )

        result = get_organization_health(db_session, user)

        assert result.rules.status == "unavailable"
        assert result.files.status == "available"

    def test_no_fabricated_zero_on_failure(self, db_session, user, test_rules, watch_folder, monkeypatch):
        # A genuine zero (no duplicates found) and an unavailable failure
        # must never look the same -- the message/status field is what
        # tells them apart, never a silent 0.
        monkeypatch.setattr(
            health_service, "build_duplicate_groups_result", lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
        )

        result = get_organization_health(db_session, user)

        assert result.duplicates.groups == 0
        assert result.duplicates.status == "unavailable"


class TestNoAIInvolvement:
    def test_no_ai_provider_function_is_called(self, db_session, user, test_rules, watch_folder, monkeypatch):
        from services import ai_provider

        def _explode(*a, **k):
            raise AssertionError("Health aggregation must never call an AI provider")

        monkeypatch.setattr(ai_provider, "generate_rule_completion", _explode)
        monkeypatch.setattr(ai_provider, "generate_suggestion_completion", _explode)
        monkeypatch.setattr(ai_provider, "generate_search_completion", _explode)

        (watch_folder / "a.txt").write_bytes(b"content")
        get_organization_health(db_session, user)  # must not raise


class TestNoMutation:
    def test_never_writes_activity_log(self, db_session, user, test_rules, watch_folder):
        (watch_folder / "invoice_1.pdf").write_bytes(b"content")
        (watch_folder / "b.bin").write_bytes(b"same")
        (watch_folder / "c.bin").write_bytes(b"same")

        get_organization_health(db_session, user)

        assert db_session.activity_log.count_documents({}) == 0

    def test_never_writes_agent_commands(self, db_session, user, test_rules, watch_folder):
        get_organization_health(db_session, user)
        assert db_session.agent_commands.count_documents({}) == 0

    def test_never_modifies_rules(self, db_session, user, test_rules):
        from rules import rule_engine as rule_engine_module

        before = dict(rule_engine_module._test_engine_override.rules)
        get_organization_health(db_session, user)
        assert rule_engine_module._test_engine_override.rules == before

    def test_never_touches_a_real_file(self, db_session, user, test_rules, watch_folder):
        f = watch_folder / "a.txt"
        f.write_bytes(b"content")
        before = f.read_bytes()

        get_organization_health(db_session, user)

        assert f.exists()
        assert f.read_bytes() == before


class TestResponseShape:
    def test_generated_at_and_agent_connected_fields(self, db_session, user, test_rules):
        result = get_organization_health(db_session, user)
        assert result.agent_connected is False
        assert result.generated_at.tzinfo is not None
