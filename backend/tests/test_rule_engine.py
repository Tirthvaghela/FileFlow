import json

import pytest

from rules.rule_engine import RuleEngine

DOC_ID = "test-rule-engine"

RULES = {
    "categories": {
        "Documents": [".pdf", ".txt"],
        "Images": [".jpg", ".png"],
    },
    "extension_rules": {".py": "Python Projects"},
    "keyword_rules": [
        {"keyword": "invoice", "folder": "Finance Folder"},
    ],
    "large_file_threshold_mb": 1,
    "large_file_folder": "Large Files",
    "archive_after_days": 30,
    "archive_folder": "Archive",
    "default_category": "Others",
    "enable_timestamp_rename": False,
    "timestamp_rename_categories": [],
}


@pytest.fixture()
def engine(db_session, watch_folder):
    # `watch_folder` (from conftest) monkeypatches settings.WATCH_FOLDER to
    # an isolated tmp dir -- classify()'s containment check depends on it,
    # so tests must never run against the developer's real .env WATCH_FOLDER.
    # `db_session` is this test's own disposable Mongo database, so seeding
    # never touches the real rules document either.
    return RuleEngine(
        db_session, doc_id=DOC_ID, watch_root=watch_folder, seed=json.loads(json.dumps(RULES))
    )


def test_classify_by_extension(engine):
    assert engine.classify("report.pdf", 100) == "Documents"


def test_classify_falls_back_to_auto_generated_folder_for_unmapped_extension(engine):
    assert engine.classify("archive.zip", 100) == "ZIP Files"


def test_classify_falls_back_to_default_category_with_auto_organize_disabled(engine):
    engine.rules["auto_organize_unknown_extensions"] = False
    assert engine.classify("archive.zip", 100) == "Others"


def test_keyword_rule_wins_over_extension_category(engine):
    # "Invoice.pdf" would map to Documents by extension alone; the keyword
    # rule must take priority over the extension-based category mapping.
    assert engine.classify("Invoice_March.pdf", 100) == "Finance Folder"


def test_keyword_match_is_case_insensitive(engine):
    assert engine.classify("INVOICE_2026.pdf", 100) == "Finance Folder"


def test_extension_rule_wins_over_category_mapping(engine):
    assert engine.classify("script.py", 100) == "Python Projects"


def test_large_file_threshold_overrides_category(engine):
    one_mb = 1024 * 1024
    assert engine.classify("photo.jpg", one_mb + 1) == "Large Files"


def test_large_file_threshold_yields_to_keyword_rule(engine):
    one_mb = 1024 * 1024
    assert engine.classify("invoice_scan.jpg", one_mb + 1) == "Finance Folder"


def test_file_under_threshold_uses_normal_category(engine):
    assert engine.classify("photo.jpg", 100) == "Images"


def test_large_file_enabled_defaults_true_when_field_is_absent(engine):
    # BASE_RULES never sets large_file_enabled -- classify() must treat a
    # missing key as "on" (matches RulesOut's large_file_enabled default).
    assert "large_file_enabled" not in engine.rules
    one_mb = 1024 * 1024
    assert engine.classify("photo.jpg", one_mb + 1) == "Large Files"


def test_large_file_enabled_false_suppresses_the_size_rule(engine):
    engine.rules["large_file_enabled"] = False
    one_mb = 1024 * 1024

    # falls through to the normal category mapping instead of Large Files
    assert engine.classify("photo.jpg", one_mb + 1) == "Images"


def test_large_file_enabled_true_still_applies_the_size_rule(engine):
    engine.rules["large_file_enabled"] = True
    one_mb = 1024 * 1024

    assert engine.classify("photo.jpg", one_mb + 1) == "Large Files"


def test_unknown_extension_gets_its_own_auto_generated_folder(engine):
    assert engine.classify("photo.heic", 100) == "HEIC Files"


def test_auto_organize_disabled_falls_back_to_default_category(engine):
    engine.rules["auto_organize_unknown_extensions"] = False
    assert engine.classify("photo.heic", 100) == "Others"


def test_file_with_no_extension_uses_default_category(engine):
    assert engine.classify("README", 100) == "Others"


def test_should_timestamp_rename_respects_flags(engine):
    assert engine.should_timestamp_rename("Images") is False

    engine.rules["enable_timestamp_rename"] = True
    engine.rules["timestamp_rename_categories"] = ["Images"]

    assert engine.should_timestamp_rename("Images") is True
    assert engine.should_timestamp_rename("Documents") is False


def test_extension_rule_pointing_outside_watch_folder_is_ignored(engine, watch_folder, tmp_path):
    outside = str(tmp_path / "outside_the_watch_folder")
    engine.rules["extension_rules"][".pdf"] = outside

    # falls back to the normal category mapping instead of following the
    # rule to a location outside the folder FileFlow was told to manage
    assert engine.classify("report.pdf", 100) == "Documents"


def test_extension_rule_pointing_to_a_subfolder_of_watch_folder_is_allowed(
    engine, watch_folder
):
    inside = str(watch_folder / "PDF")
    engine.rules["extension_rules"][".pdf"] = inside

    assert engine.classify("report.pdf", 100) == inside


def test_keyword_rule_pointing_outside_watch_folder_is_ignored(engine, tmp_path):
    outside = str(tmp_path / "elsewhere")
    engine.rules["keyword_rules"] = [{"keyword": "invoice", "folder": outside}]

    assert engine.classify("Invoice_March.pdf", 100) == "Documents"


def test_large_file_folder_pointing_outside_watch_folder_is_ignored(engine, tmp_path):
    outside = str(tmp_path / "elsewhere")
    engine.rules["large_file_folder"] = outside

    one_mb = 1024 * 1024
    assert engine.classify("photo.jpg", one_mb + 1) == "Images"


def test_save_persists_and_reload_reads_it_back(db_session, tmp_path):
    engine = RuleEngine(
        db_session, doc_id=DOC_ID, watch_root=tmp_path, seed=json.loads(json.dumps(RULES))
    )

    updated = json.loads(json.dumps(RULES))
    updated["archive_after_days"] = 7
    engine.save(updated)

    reloaded = RuleEngine(db_session, doc_id=DOC_ID, watch_root=tmp_path)
    assert reloaded.archive_after_days == 7


class TestRegexRules:
    def test_matches_a_pattern_against_the_filename(self, engine):
        engine.rules["regex_rules"] = [{"pattern": r"^IMG_\d+", "folder": "Camera"}]
        assert engine.classify("IMG_2024.jpg", 100) == "Camera"

    def test_a_non_matching_pattern_falls_through_to_normal_classification(self, engine):
        engine.rules["regex_rules"] = [{"pattern": r"^IMG_\d+", "folder": "Camera"}]
        assert engine.classify("report.pdf", 100) == "Documents"

    def test_an_invalid_pattern_is_skipped_rather_than_raising(self, engine):
        # RulesOut validates patterns at the API boundary, but classify()
        # itself must stay defensive -- a bad pattern must never take down
        # every file being organized, it should just never match.
        engine.rules["regex_rules"] = [{"pattern": "[unclosed", "folder": "Camera"}]
        assert engine.classify("report.pdf", 100) == "Documents"

    def test_keyword_rules_still_win_over_regex_rules(self, engine):
        engine.rules["regex_rules"] = [{"pattern": r"\.pdf$", "folder": "PDF Dump"}]
        # "invoice" keyword rule already exists in the base RULES fixture.
        assert engine.classify("invoice_march.pdf", 100) == "Finance Folder"


class TestContentKeywordRules:
    def test_matches_a_keyword_found_inside_the_file(self, engine, watch_folder):
        engine.rules["content_keyword_rules"] = [{"keyword": "confidential", "folder": "Private"}]
        target = watch_folder / "notes.txt"
        target.write_text("This document is CONFIDENTIAL -- do not share.")

        assert engine.classify("notes.txt", 100, file_path=target) == "Private"

    def test_never_matches_without_a_real_file_path(self, engine, watch_folder):
        # Callers that only have a bare filename (a dry-run preview, older
        # code paths) can't offer file content -- the rule must be a no-op
        # rather than erroring, falling through to normal classification.
        engine.rules["content_keyword_rules"] = [{"keyword": "confidential", "folder": "Private"}]
        assert engine.classify("notes.txt", 100) == "Documents"

    def test_a_file_without_the_keyword_falls_through(self, engine, watch_folder):
        engine.rules["content_keyword_rules"] = [{"keyword": "confidential", "folder": "Private"}]
        target = watch_folder / "notes.txt"
        target.write_text("Just a normal grocery list.")

        assert engine.classify("notes.txt", 100, file_path=target) == "Documents"

    def test_binary_content_does_not_raise(self, engine, watch_folder):
        engine.rules["content_keyword_rules"] = [{"keyword": "confidential", "folder": "Private"}]
        target = watch_folder / "photo.jpg"
        target.write_bytes(bytes(range(256)) * 4)

        assert engine.classify("photo.jpg", 100, file_path=target) == "Images"


class TestDateRules:
    def test_matches_a_file_older_than_the_threshold(self, engine, watch_folder):
        import os
        import time

        engine.rules["date_rules"] = [{"older_than_days": 30, "folder": "Old Stuff"}]
        target = watch_folder / "readme"  # no extension -- would default to "Others"
        target.write_text("hi")
        old = time.time() - 45 * 86400
        os.utime(target, (old, old))

        assert engine.classify("readme", 100, file_path=target) == "Old Stuff"

    def test_a_recent_file_does_not_match(self, engine, watch_folder):
        engine.rules["date_rules"] = [{"older_than_days": 30, "folder": "Old Stuff"}]
        target = watch_folder / "readme"
        target.write_text("hi")

        assert engine.classify("readme", 100, file_path=target) == "Others"


class TestClassificationExplanation:
    """classify_explained() must describe the exact same decision
    classify() makes -- never a second, independently re-run evaluation --
    for every rule type FileFlow actually supports, and must never
    attribute a match to a rule that didn't really match."""

    def test_keyword_match_explanation(self, engine):
        result = engine.classify_explained("Invoice_March.pdf", 100)

        assert result["destination"] == "Finance Folder"
        assert result["match_type"] == "keyword"
        assert result["matched_value"] == "invoice"
        assert result["rule_name"] == 'Keyword "invoice"'
        assert result["priority"] == 1

    def test_regex_match_explanation(self, engine):
        engine.rules["regex_rules"] = [{"pattern": r"^IMG_\d+", "folder": "Camera"}]

        result = engine.classify_explained("IMG_2024.jpg", 100)

        assert result["destination"] == "Camera"
        assert result["match_type"] == "regex"
        assert result["matched_value"] == r"^IMG_\d+"
        assert result["priority"] == 2

    def test_content_keyword_match_explanation(self, engine, watch_folder):
        engine.rules["content_keyword_rules"] = [{"keyword": "confidential", "folder": "Private"}]
        target = watch_folder / "notes.txt"
        target.write_text("This document is CONFIDENTIAL -- do not share.")

        result = engine.classify_explained("notes.txt", 100, file_path=target)

        assert result["destination"] == "Private"
        assert result["match_type"] == "content_keyword"
        assert result["matched_value"] == "confidential"
        assert result["priority"] == 3

    def test_extension_rule_explanation(self, engine):
        result = engine.classify_explained("script.py", 100)

        assert result["destination"] == "Python Projects"
        assert result["match_type"] == "extension"
        assert result["matched_value"] == ".py"
        assert result["rule_name"] == 'Extension ".py"'
        assert result["priority"] == 4

    def test_large_file_explanation(self, engine):
        one_mb = 1024 * 1024
        result = engine.classify_explained("photo.jpg", one_mb + 1)

        assert result["destination"] == "Large Files"
        assert result["match_type"] == "large_file"
        assert result["priority"] == 5

    def test_date_rule_explanation(self, engine, watch_folder):
        import os
        import time

        engine.rules["date_rules"] = [{"older_than_days": 30, "folder": "Old Stuff"}]
        target = watch_folder / "readme"
        target.write_text("hi")
        old = time.time() - 45 * 86400
        os.utime(target, (old, old))

        result = engine.classify_explained("readme", 100, file_path=target)

        assert result["destination"] == "Old Stuff"
        assert result["match_type"] == "date"
        assert result["priority"] == 6

    def test_category_mapping_explanation(self, engine):
        result = engine.classify_explained("report.pdf", 100)

        assert result["destination"] == "Documents"
        assert result["match_type"] == "category"
        assert result["matched_value"] == ".pdf"
        assert result["rule_name"] == 'Category "Documents"'
        assert result["priority"] == 7

    def test_auto_extension_grouping_explanation(self, engine):
        result = engine.classify_explained("archive.zip", 100)

        assert result["destination"] == "ZIP Files"
        assert result["match_type"] == "auto_extension"
        assert result["matched_value"] == ".zip"
        assert result["priority"] == 8

    def test_no_matching_rule_explanation(self, engine):
        engine.rules["auto_organize_unknown_extensions"] = False

        result = engine.classify_explained("archive.zip", 100)

        assert result["destination"] == "Others"
        assert result["match_type"] == "default"
        assert result["matched_value"] is None
        assert result["rule_name"] is None
        assert result["priority"] == 9

    def test_correct_rule_identified_when_several_keyword_rules_exist(self, engine):
        engine.rules["keyword_rules"] = [
            {"keyword": "invoice", "folder": "Finance Folder"},
            {"keyword": "report", "folder": "Reports Folder"},
        ]

        result = engine.classify_explained("Quarterly_Report.pdf", 100)

        assert result["destination"] == "Reports Folder"
        assert result["matched_value"] == "report"

    def test_a_rule_pointing_outside_the_watch_folder_is_not_attributed_as_the_match(
        self, engine, tmp_path
    ):
        # Same containment rule classify() already enforces -- the
        # explanation must agree: the invalid rule is skipped entirely,
        # never reported as if it had actually matched.
        outside = str(tmp_path / "elsewhere")
        engine.rules["keyword_rules"] = [{"keyword": "invoice", "folder": outside}]

        result = engine.classify_explained("Invoice_March.pdf", 100)

        assert result["match_type"] != "keyword"
        assert result["destination"] == "Documents"

    def test_explanation_destination_always_matches_classify(self, engine, watch_folder):
        # classify() is a thin wrapper over classify_explained() -- the two
        # must never disagree, for any input.
        cases = [
            ("Invoice_March.pdf", 100),
            ("script.py", 100),
            ("photo.jpg", 1024 * 1024 + 1),
            ("archive.zip", 100),
            ("readme", 100),
        ]
        for filename, size in cases:
            assert engine.classify(filename, size) == engine.classify_explained(filename, size)[
                "destination"
            ]

    def test_never_matches_without_a_real_file_path(self, engine):
        engine.rules["date_rules"] = [{"older_than_days": 30, "folder": "Old Stuff"}]
        assert engine.classify("readme", 100) == "Others"

    def test_overrides_the_generic_extension_category_like_large_file_already_does(
        self, engine, watch_folder
    ):
        # date_rules is checked before the generic categories grouping --
        # same priority large_file_threshold already has (see
        # test_large_file_threshold_overrides_category above), since both
        # are explicit, attribute-based rules the user configured on
        # purpose, not the catch-all extension->category mapping.
        import os
        import time

        engine.rules["date_rules"] = [{"older_than_days": 30, "folder": "Old Stuff"}]
        target = watch_folder / "report.pdf"
        target.write_text("hi")
        old = time.time() - 45 * 86400
        os.utime(target, (old, old))

        assert engine.classify("report.pdf", 100, file_path=target) == "Old Stuff"

    def test_a_file_exactly_at_the_day_boundary_matches(self, engine, watch_folder):
        # age_days >= older_than_days -- the boundary itself is inclusive.
        import os
        import time

        engine.rules["date_rules"] = [{"older_than_days": 30, "folder": "Old Stuff"}]
        target = watch_folder / "readme"
        target.write_text("hi")
        exactly_30_days = time.time() - 30 * 86400
        os.utime(target, (exactly_30_days, exactly_30_days))

        assert engine.classify("readme", 100, file_path=target) == "Old Stuff"

    def test_a_file_one_second_short_of_the_boundary_does_not_match(self, engine, watch_folder):
        import os
        import time

        engine.rules["date_rules"] = [{"older_than_days": 30, "folder": "Old Stuff"}]
        target = watch_folder / "readme"
        target.write_text("hi")
        one_second_short = time.time() - (30 * 86400 - 1)
        os.utime(target, (one_second_short, one_second_short))

        assert engine.classify("readme", 100, file_path=target) == "Others"

    def test_a_file_one_second_past_the_boundary_matches(self, engine, watch_folder):
        import os
        import time

        engine.rules["date_rules"] = [{"older_than_days": 30, "folder": "Old Stuff"}]
        target = watch_folder / "readme"
        target.write_text("hi")
        one_second_past = time.time() - (30 * 86400 + 1)
        os.utime(target, (one_second_past, one_second_past))

        assert engine.classify("readme", 100, file_path=target) == "Old Stuff"

    def test_a_future_mtime_never_matches(self, engine, watch_folder):
        # A clock skew or a file freshly restored with a future timestamp
        # must not be treated as "old" -- age_days would go negative,
        # which is still < any non-negative older_than_days.
        import os
        import time

        engine.rules["date_rules"] = [{"older_than_days": 30, "folder": "Old Stuff"}]
        target = watch_folder / "readme"
        target.write_text("hi")
        one_hour_in_the_future = time.time() + 3600
        os.utime(target, (one_hour_in_the_future, one_hour_in_the_future))

        assert engine.classify("readme", 100, file_path=target) == "Others"


class TestLargeFileBoundary:
    def test_exactly_at_the_threshold_does_not_match(self, engine):
        # file_size_bytes > threshold_mb * 1024 * 1024 -- strictly greater
        # than, so a file exactly at the threshold does not count as large.
        one_mb = 1024 * 1024
        assert engine.classify("photo.jpg", one_mb, file_path=None) == "Images"

    def test_one_byte_over_the_threshold_matches(self, engine):
        one_mb = 1024 * 1024
        assert engine.classify("photo.jpg", one_mb + 1) == "Large Files"

    def test_one_byte_under_the_threshold_does_not_match(self, engine):
        one_mb = 1024 * 1024
        assert engine.classify("photo.jpg", one_mb - 1) == "Images"


class TestExtensionEdgeCases:
    def test_uppercase_extension_matches_the_lowercase_rule(self, engine):
        assert engine.classify("Report.PDF", 100) == "Documents"

    def test_a_dotfile_with_no_further_extension_has_no_extension(self, engine):
        # Path(".env").suffix == "" (pathlib treats the whole name as the
        # stem, not an extension) -- .env falls through to default_category
        # exactly like a file with no dot at all, not into some ".env"
        # bucket a naive split on "." might produce.
        assert engine.classify(".env", 100) == "Others"

    def test_a_trailing_dot_with_nothing_after_it_has_no_extension(self, engine):
        assert engine.classify("archive.", 100) == "Others"

    def test_multiple_dots_use_only_the_final_segment_as_the_extension(self, engine):
        # Path("archive.tar.gz").suffix == ".gz", not ".tar.gz" -- a rule
        # keyed on ".gz" applies, "tar" is irrelevant to matching.
        engine.rules["extension_rules"][".gz"] = "Compressed"
        assert engine.classify("archive.tar.gz", 100) == "Compressed"


class TestKeywordMatchingEdgeCases:
    def test_matches_as_a_substring_regardless_of_surrounding_punctuation(self, engine):
        assert engine.classify("my_invoice_2026.pdf", 100) == "Finance Folder"
        assert engine.classify("invoice-final.pdf", 100) == "Finance Folder"

    def test_unicode_filename_does_not_crash_and_can_still_match(self, engine):
        engine.rules["keyword_rules"].append({"keyword": "facture", "folder": "Finance FR"})
        assert engine.classify("Facture_Électricité_2026.pdf", 100) == "Finance FR"

    def test_unicode_filename_with_no_match_falls_through_normally(self, engine):
        assert engine.classify("Résumé_Final.pdf", 100) == "Documents"


class TestContentKeywordScanLimit:
    def test_a_match_well_within_the_scan_limit_is_found(self, engine, watch_folder):
        engine.rules["content_keyword_rules"] = [{"keyword": "confidential", "folder": "Private"}]
        target = watch_folder / "notes.txt"
        target.write_text("confidential " + "x" * 100)

        assert engine.classify("notes.txt", 100, file_path=target) == "Private"

    def test_a_match_past_the_scan_limit_is_not_found(self, engine, watch_folder):
        # _CONTENT_SNIFF_MAX_BYTES caps the read at 64KB -- a keyword that
        # only appears after that point must not match, matching the
        # documented "sniff the beginning" contract rather than silently
        # scanning the whole file regardless of size.
        engine.rules["content_keyword_rules"] = [{"keyword": "confidential", "folder": "Private"}]
        target = watch_folder / "notes.txt"
        target.write_text("x" * (70 * 1024) + "confidential")

        assert engine.classify("notes.txt", 100, file_path=target) == "Documents"

    def test_invalid_utf8_bytes_do_not_raise(self, engine, watch_folder):
        engine.rules["content_keyword_rules"] = [{"keyword": "confidential", "folder": "Private"}]
        target = watch_folder / "notes.txt"
        target.write_bytes(b"\xff\xfe\x00invalid utf8 \x80\x81 bytes")

        assert engine.classify("notes.txt", 100, file_path=target) == "Documents"


class TestDeterminism:
    def test_identical_rules_produce_identical_results_across_repeated_calls(self, engine):
        results = {engine.classify("report.pdf", 100) for _ in range(20)}
        assert results == {"Documents"}

    def test_dict_key_order_of_overlapping_categories_determines_the_winner_stably(
        self, engine
    ):
        # If two categories both happen to list the same extension (a
        # data-integrity edge case, not something the UI is meant to
        # produce), Python dicts preserve insertion order -- the first
        # category inserted containing that extension wins, consistently,
        # rather than varying run to run.
        engine.rules["categories"] = {
            "First": [".weird"],
            "Second": [".weird"],
        }
        results = {engine.classify("file.weird", 100) for _ in range(20)}
        assert results == {"First"}
