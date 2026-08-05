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
