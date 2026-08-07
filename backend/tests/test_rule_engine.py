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
