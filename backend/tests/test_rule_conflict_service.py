import pytest

from services.rule_conflict_service import (
    MAX_CONFLICTS_RETURNED,
    _build_candidate,
    _regex_candidate_from_other,
    _valid_rules,
    analyze_conflicts,
)


def _types(result):
    return [c.type for c in result.conflicts]


class TestNoConflicts:
    def test_empty_rules_produce_an_empty_result(self, watch_folder):
        result = analyze_conflicts({}, watch_folder)
        assert result.conflicts == []
        assert result.total == 0
        assert result.info == 0
        assert result.warnings == 0
        assert result.high == 0
        assert result.rules_checked == 0

    def test_a_single_rule_produces_no_conflicts(self, watch_folder):
        rules = {"keyword_rules": [{"keyword": "invoice", "folder": "Finance"}]}
        result = analyze_conflicts(rules, watch_folder)
        assert result.conflicts == []
        assert result.rules_checked == 1

    def test_unrelated_keywords_produce_no_shadow_claim_between_them(self, watch_folder):
        # Neither is a substring of the other -- no relationship can be
        # proven, so nothing is claimed about this specific pair.
        rules = {
            "keyword_rules": [
                {"keyword": "invoice", "folder": "Finance"},
                {"keyword": "photo", "folder": "Images"},
            ]
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.conflicts == []


class TestCrossTypeOverlap:
    def test_keyword_and_extension_overlap_is_detected(self, watch_folder):
        # The Phase 26 demo scenario: keyword "invoice" + extension .pdf.
        rules = {
            "keyword_rules": [{"keyword": "invoice", "folder": "Finance/Invoices"}],
            "extension_rules": {".pdf": "Documents/PDF"},
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.total == 1
        c = result.conflicts[0]
        assert c.type == "precedence_overlap"
        assert c.severity == "warning"
        assert c.example.filename == "invoice.pdf"
        assert c.example.destination == "Finance/Invoices"
        assert c.example.winning_rule == 'Keyword "invoice"'
        assert "invoice.pdf" in c.message
        assert "Keyword rules are evaluated before extension rules." in c.message

    def test_keyword_and_extension_same_destination_is_only_info(self, watch_folder):
        rules = {
            "keyword_rules": [{"keyword": "invoice", "folder": "Finance"}],
            "extension_rules": {".pdf": "Finance"},
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.total == 1
        c = result.conflicts[0]
        assert c.type == "overlap"
        assert c.severity == "info"

    def test_winning_destination_matches_classify_file_explained(self, watch_folder):
        from rules.classifier import classify_file_explained

        rules = {
            "keyword_rules": [{"keyword": "invoice", "folder": "Finance/Invoices"}],
            "extension_rules": {".pdf": "Documents/PDF"},
        }
        result = analyze_conflicts(rules, watch_folder)
        explanation = classify_file_explained(rules, "invoice.pdf", 100, watch_folder)
        assert result.conflicts[0].example.destination == explanation["destination"]
        assert explanation["match_type"] == "keyword"

    def test_extension_and_large_file_overlap_is_detected(self, watch_folder):
        rules = {
            "extension_rules": {".iso": "Disk Images"},
            "large_file_threshold_mb": 500,
            "large_file_folder": "Large Files",
            "large_file_enabled": True,
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.total == 1
        c = result.conflicts[0]
        assert c.type == "precedence_overlap"
        assert c.example.filename.endswith(".iso")

    def test_disabled_large_file_rule_never_participates(self, watch_folder):
        rules = {
            "extension_rules": {".iso": "Disk Images"},
            "large_file_threshold_mb": 500,
            "large_file_folder": "Large Files",
            "large_file_enabled": False,
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.conflicts == []

    def test_regex_and_extension_overlap_detected_where_provable(self, watch_folder):
        # The synthetic candidate built from the extension rule alone is
        # "sample.pdf" -- this pattern must actually match that string for
        # the overlap to be provable/claimed.
        rules = {
            "regex_rules": [{"pattern": r"\.pdf$", "folder": "Finance/Invoices"}],
            "extension_rules": {".pdf": "Documents/PDF"},
        }
        result = analyze_conflicts(rules, watch_folder)
        precedence = [c for c in result.conflicts if c.type == "precedence_overlap"]
        assert len(precedence) == 1
        assert precedence[0].example.winning_rule.startswith("Regex pattern")

    def test_regex_that_cannot_match_the_generated_candidate_produces_no_claim(self, watch_folder):
        # The candidate built from the extension rule ("sample.pdf") never
        # satisfies this anchored pattern -- no overlap is claimed, since
        # none was demonstrated.
        rules = {
            "regex_rules": [{"pattern": r"^ONLY_THIS_EXACT_NAME$", "folder": "Weird"}],
            "extension_rules": {".pdf": "Documents/PDF"},
        }
        result = analyze_conflicts(rules, watch_folder)
        assert [c for c in result.conflicts if c.type in ("overlap", "precedence_overlap")] == []

    def test_regex_and_keyword_overlap_detected(self, watch_folder):
        rules = {
            "regex_rules": [{"pattern": r"invoice", "folder": "Finance A"}],
            "keyword_rules": [{"keyword": "invoice", "folder": "Finance B"}],
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.total == 1
        assert result.conflicts[0].type == "precedence_overlap"


class TestSameListKeywordConflicts:
    def test_keyword_keyword_overlap_detected_where_provable(self, watch_folder):
        # "receipt" is a substring of "gstreceipt" -- every file matching
        # the later rule also matches the earlier one, evaluated first.
        rules = {
            "keyword_rules": [
                {"keyword": "receipt", "folder": "Finance/Receipts"},
                {"keyword": "gstreceipt", "folder": "Finance/GST"},
            ]
        }
        result = analyze_conflicts(rules, watch_folder)
        shadow = [c for c in result.conflicts if c.type == "shadowed_rule"]
        assert len(shadow) == 1
        assert shadow[0].severity == "high"
        assert shadow[0].example.winning_rule == 'Keyword "receipt"'

    def test_identical_keyword_rules_same_destination_are_redundant(self, watch_folder):
        rules = {
            "keyword_rules": [
                {"keyword": "invoice", "folder": "Finance"},
                {"keyword": "invoice", "folder": "Finance"},
            ]
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.total == 1
        c = result.conflicts[0]
        assert c.type == "redundant_rule"
        assert c.severity == "info"

    def test_identical_keyword_rules_different_destination_is_high_severity_shadow(self, watch_folder):
        rules = {
            "keyword_rules": [
                {"keyword": "invoice", "folder": "Finance A"},
                {"keyword": "invoice", "folder": "Finance B"},
            ]
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.total == 1
        c = result.conflicts[0]
        assert c.type == "shadowed_rule"
        assert c.severity == "high"

    def test_content_keyword_rules_use_the_same_containment_logic(self, watch_folder):
        rules = {
            "content_keyword_rules": [
                {"keyword": "gst", "folder": "Finance/GST"},
                {"keyword": "gstreceipt", "folder": "Finance/Receipts"},
            ]
        }
        result = analyze_conflicts(rules, watch_folder)
        shadow = [c for c in result.conflicts if c.type == "shadowed_rule"]
        assert len(shadow) == 1
        assert shadow[0].rules[0].rule_type == "content_keyword"


class TestSameListRegexConflicts:
    def test_identical_regex_patterns_different_destination_is_shadowed(self, watch_folder):
        rules = {
            "regex_rules": [
                {"pattern": r"^IMG_\d+", "folder": "Camera A"},
                {"pattern": r"^IMG_\d+", "folder": "Camera B"},
            ]
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.total == 1
        assert result.conflicts[0].type == "shadowed_rule"
        assert result.conflicts[0].severity == "high"

    def test_different_regex_patterns_are_never_compared_structurally(self, watch_folder):
        rules = {
            "regex_rules": [
                {"pattern": r"^IMG_\d+", "folder": "Camera A"},
                {"pattern": r"^SCAN_\d+", "folder": "Camera B"},
            ]
        }
        result = analyze_conflicts(rules, watch_folder)
        assert [c for c in result.conflicts if "IMG" in str(c.rules) and "SCAN" in str(c.rules)] == []


class TestSameListDateConflicts:
    def test_a_broader_threshold_shadows_a_narrower_later_one(self, watch_folder):
        rules = {
            "date_rules": [
                {"older_than_days": 30, "folder": "Old Stuff A"},
                {"older_than_days": 90, "folder": "Old Stuff B"},
            ]
        }
        result = analyze_conflicts(rules, watch_folder)
        shadow = [c for c in result.conflicts if c.type == "shadowed_rule"]
        assert len(shadow) == 1
        assert shadow[0].example.filename is None
        assert shadow[0].example.winning_rule == "File age (over 30 days old)"

    def test_a_narrower_threshold_first_does_not_shadow_a_broader_later_one(self, watch_folder):
        # 90 days is NOT a superset of 30 days -- no claim can be proven in
        # this direction.
        rules = {
            "date_rules": [
                {"older_than_days": 90, "folder": "Old Stuff A"},
                {"older_than_days": 30, "folder": "Old Stuff B"},
            ]
        }
        result = analyze_conflicts(rules, watch_folder)
        assert [c for c in result.conflicts if c.type == "shadowed_rule"] == []

    def test_identical_thresholds_same_destination_are_redundant(self, watch_folder):
        rules = {
            "date_rules": [
                {"older_than_days": 30, "folder": "Old Stuff"},
                {"older_than_days": 30, "folder": "Old Stuff"},
            ]
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.conflicts[0].type == "redundant_rule"


class TestUnverifiableOverlap:
    def test_content_keyword_rules_alongside_other_rules_are_disclosed_as_unverifiable(
        self, watch_folder
    ):
        rules = {
            "content_keyword_rules": [{"keyword": "confidential", "folder": "Private"}],
            "extension_rules": {".pdf": "Documents"},
        }
        result = analyze_conflicts(rules, watch_folder)
        unverifiable = [c for c in result.conflicts if c.type == "unverifiable_overlap"]
        assert len(unverifiable) == 1
        assert "content" in unverifiable[0].message.lower()
        assert unverifiable[0].severity == "info"

    def test_date_rules_alongside_other_rules_are_disclosed_as_unverifiable(self, watch_folder):
        rules = {
            "date_rules": [{"older_than_days": 30, "folder": "Old Stuff"}],
            "keyword_rules": [{"keyword": "invoice", "folder": "Finance"}],
        }
        result = analyze_conflicts(rules, watch_folder)
        unverifiable = [c for c in result.conflicts if c.type == "unverifiable_overlap"]
        assert len(unverifiable) == 1
        assert "age" in unverifiable[0].message.lower() or "date" in unverifiable[0].message.lower()

    def test_no_unverifiable_notice_when_it_is_the_only_rule_type_present(self, watch_folder):
        # Nothing else exists for it to possibly overlap with.
        rules = {"content_keyword_rules": [{"keyword": "confidential", "folder": "Private"}]}
        result = analyze_conflicts(rules, watch_folder)
        assert result.conflicts == []

    def test_wording_says_potential_not_certain(self, watch_folder):
        rules = {
            "date_rules": [{"older_than_days": 30, "folder": "Old Stuff"}],
            "keyword_rules": [{"keyword": "invoice", "folder": "Finance"}],
        }
        result = analyze_conflicts(rules, watch_folder)
        notice = next(c for c in result.conflicts if c.type == "unverifiable_overlap")
        assert "could overlap" in notice.message
        assert "can't be checked" in notice.message


class TestInvalidDestinationRulesAreInvisible:
    def test_a_rule_pointing_outside_the_watch_folder_never_participates(self, watch_folder, tmp_path):
        outside = str(tmp_path / "elsewhere")
        rules = {
            "keyword_rules": [{"keyword": "invoice", "folder": outside}],
            "extension_rules": {".pdf": "Documents/PDF"},
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.conflicts == []
        assert result.rules_checked == 1  # only the valid extension rule counts


class TestDisabledRulesAreIgnored:
    def test_disabled_keyword_rules_are_never_analyzed(self, watch_folder):
        rules = {
            "disabled_keyword_rules": [{"keyword": "invoice", "folder": "Finance"}],
            "extension_rules": {".pdf": "Documents/PDF"},
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.conflicts == []
        assert result.rules_checked == 1


class TestRegexSafety:
    def test_an_invalid_pattern_is_skipped_rather_than_raising(self, watch_folder):
        # RulesOut already rejects an invalid pattern before it can ever be
        # saved -- this defends the service itself against being handed one
        # directly, the same defensive posture classify_file_explained
        # already takes.
        rules = {
            "regex_rules": [{"pattern": "[unclosed", "folder": "Weird"}],
            "extension_rules": {".pdf": "Documents"},
        }
        result = analyze_conflicts(rules, watch_folder)
        assert result.conflicts == []


class TestTruncation:
    def test_conflicts_are_capped_and_truncated_flag_is_set(self, watch_folder):
        keywords = [{"keyword": f"kw{i}", "folder": f"Folder{i}"} for i in range(20)]
        extensions = {f".ext{i}": f"ExtFolder{i}" for i in range(20)}
        rules = {"keyword_rules": keywords, "extension_rules": extensions}
        result = analyze_conflicts(rules, watch_folder)
        assert len(result.conflicts) == MAX_CONFLICTS_RETURNED
        assert result.total == MAX_CONFLICTS_RETURNED
        assert result.truncated is True


class TestCandidateGeneration:
    def test_build_candidate_combines_keyword_and_extension(self):
        result = _build_candidate(
            "keyword", {"keyword": "invoice", "folder": "F"}, "extension", {"extension": ".pdf", "folder": "F"}
        )
        assert result == ("invoice.pdf", 2048)

    def test_build_candidate_uses_large_file_threshold_for_size(self):
        result = _build_candidate(
            "keyword",
            {"keyword": "invoice", "folder": "F"},
            "large_file",
            {"threshold_mb": 10, "folder": "F"},
        )
        name, size = result
        assert name == "invoice.dat"
        assert size == 10 * 1024 * 1024 + 1

    def test_build_candidate_returns_none_for_non_generatable_pair(self):
        assert _build_candidate("regex", {"pattern": "x"}, "extension", {"extension": ".pdf"}) is None

    def test_regex_candidate_from_extension(self):
        assert _regex_candidate_from_other("extension", {"extension": ".pdf"}) == (
            "sample.pdf",
            2048,
        )

    def test_regex_candidate_from_unknown_type_is_none(self):
        assert _regex_candidate_from_other("content_keyword", {}) is None


class TestValidRulesFiltering:
    def test_large_file_with_no_threshold_is_excluded(self, watch_folder):
        normalized = _valid_rules({"large_file_folder": "Large Files"}, watch_folder)
        assert normalized["large_file"] == []

    def test_extension_rules_dict_is_normalized_to_a_list(self, watch_folder):
        normalized = _valid_rules({"extension_rules": {".pdf": "Documents"}}, watch_folder)
        assert normalized["extension"] == [{"extension": ".pdf", "folder": "Documents"}]


class TestRegressionAgainstRealClassifier:
    def test_analyzing_conflicts_never_mutates_the_rules_dict_passed_in(self, watch_folder):
        import copy

        rules = {
            "keyword_rules": [{"keyword": "invoice", "folder": "Finance"}],
            "extension_rules": {".pdf": "Documents"},
        }
        before = copy.deepcopy(rules)
        analyze_conflicts(rules, watch_folder)
        assert rules == before

    def test_classification_behavior_is_unaffected_by_running_conflict_analysis(self, watch_folder):
        from rules.classifier import classify_file

        rules = {
            "keyword_rules": [{"keyword": "invoice", "folder": "Finance/Invoices"}],
            "extension_rules": {".pdf": "Documents/PDF"},
        }
        before = classify_file(rules, "invoice.pdf", 100, watch_folder)
        analyze_conflicts(rules, watch_folder)
        after = classify_file(rules, "invoice.pdf", 100, watch_folder)
        assert before == after == "Finance/Invoices"
