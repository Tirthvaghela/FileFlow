from pathlib import Path

from automation import organizer
from automation.organizer import (
    build_final_name,
    compute_hash,
    organize_existing_files,
    process_file,
    reclassify_file,
    resolve_destination,
    undo_last_operation,
)
from models.models import Document


def _write(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


class TestResolveDestination:
    def test_returns_moved_when_destination_is_free(self, tmp_path, test_engine):
        dest_folder = tmp_path / "Documents"
        dest_folder.mkdir()
        source = _write(tmp_path / "a.txt", "hello")

        dest_path, action = resolve_destination(dest_folder, "a.txt", source, test_engine)

        assert action == "moved"
        assert dest_path == dest_folder / "a.txt"

    def test_returns_duplicate_skipped_when_content_matches(self, tmp_path, test_engine):
        dest_folder = tmp_path / "Documents"
        dest_folder.mkdir()
        _write(dest_folder / "a.txt", "hello")
        source = _write(tmp_path / "a.txt", "hello")

        dest_path, action = resolve_destination(dest_folder, "a.txt", source, test_engine)

        assert action == "duplicate_skipped"
        assert dest_path is None

    def test_renames_with_counter_when_content_differs(self, tmp_path, test_engine):
        dest_folder = tmp_path / "Documents"
        dest_folder.mkdir()
        _write(dest_folder / "a.txt", "existing content")
        source = _write(tmp_path / "a.txt", "different content")

        dest_path, action = resolve_destination(dest_folder, "a.txt", source, test_engine)

        assert action == "renamed_and_moved"
        assert dest_path == dest_folder / "a (1).txt"

    def test_renames_skip_taken_counters(self, tmp_path, test_engine):
        dest_folder = tmp_path / "Documents"
        dest_folder.mkdir()
        _write(dest_folder / "a.txt", "existing")
        _write(dest_folder / "a (1).txt", "existing-1")
        source = _write(tmp_path / "a.txt", "new content")

        dest_path, action = resolve_destination(dest_folder, "a.txt", source, test_engine)

        assert action == "renamed_and_moved"
        assert dest_path == dest_folder / "a (2).txt"


def test_compute_hash_matches_for_identical_content(tmp_path):
    a = _write(tmp_path / "a.txt", "same content")
    b = _write(tmp_path / "b.txt", "same content")
    assert compute_hash(a) == compute_hash(b)


def test_compute_hash_differs_for_different_content(tmp_path):
    a = _write(tmp_path / "a.txt", "content one")
    b = _write(tmp_path / "b.txt", "content two")
    assert compute_hash(a) != compute_hash(b)


class TestProcessFile:
    def test_routes_to_keyword_folder_over_extension_category(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "Invoice_March.pdf", "invoice contents")

        log = process_file(source, db_session, test_user)

        assert log.action == "moved"
        assert log.category == "Finance Folder"
        assert (watch_folder / "Finance Folder" / "Invoice_March.pdf").exists()
        assert not source.exists()

    def test_routes_by_extension_rule(self, watch_folder, test_rules, db_session, test_user):
        source = _write(watch_folder / "script.py", "print('hi')")

        log = process_file(source, db_session, test_user)

        assert log.category == "Python Projects"
        assert (watch_folder / "Python Projects" / "script.py").exists()

    def test_unmapped_extension_gets_auto_generated_folder(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "archive.zip", "zip bytes")

        log = process_file(source, db_session, test_user)

        assert log.category == "ZIP Files"
        assert (watch_folder / "ZIP Files" / "archive.zip").exists()

    def test_falls_back_to_default_category_with_no_extension(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "README", "no extension here")

        log = process_file(source, db_session, test_user)

        assert log.category == "Others"

    def test_duplicate_file_is_skipped_not_moved(
        self, watch_folder, test_rules, db_session, test_user
    ):
        first_source = _write(watch_folder / "notes.txt", "same text")
        process_file(first_source, db_session, test_user)

        second_source = _write(watch_folder / "notes.txt", "same text")
        log = process_file(second_source, db_session, test_user)

        assert log.action == "duplicate_skipped"
        # non-destructive: the duplicate is left exactly where it landed
        assert second_source.exists()

    def test_ignored_suffix_is_left_alone(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "download.crdownload", "partial")

        result = process_file(source, db_session, test_user)

        assert result is None
        assert source.exists()

    def test_log_is_persisted_to_db(self, watch_folder, test_rules, db_session, test_user):
        source = _write(watch_folder / "notes.txt", "hi")
        process_file(source, db_session, test_user)

        rows = [Document(r) for r in db_session.activity_log.find()]
        assert len(rows) == 1
        assert rows[0].original_filename == "notes.txt"
        assert rows[0].undone is False
        assert rows[0].user_id == test_user["id"]


class TestProcessFileUiPathWiring:
    def test_uses_the_uipath_result_when_it_reports_success(
        self, watch_folder, test_rules, db_session, test_user, monkeypatch
    ):
        calls = []

        def fake_uipath(source, dest_folder, final_name):
            calls.append((source, dest_folder, final_name))
            dest_folder.mkdir(parents=True, exist_ok=True)
            dest = dest_folder / final_name
            source.rename(dest)  # simulate UiPath having performed the move
            return dest

        monkeypatch.setattr(organizer, "execute_move_via_uipath", fake_uipath)
        source = _write(watch_folder / "notes.txt", "hi")

        log = process_file(source, db_session, test_user)

        assert len(calls) == 1
        assert log.category == "Documents"
        assert (watch_folder / "Documents" / "notes.txt").exists()
        assert not source.exists()

    def test_falls_back_to_python_move_when_uipath_returns_none(
        self, watch_folder, test_rules, db_session, test_user, monkeypatch
    ):
        # The default/disabled state already exercises this path implicitly
        # (every other test in this file runs with UiPath off) -- this test
        # makes the fallback explicit and asserts on it directly.
        monkeypatch.setattr(organizer, "execute_move_via_uipath", lambda *a: None)
        source = _write(watch_folder / "notes.txt", "hi")

        log = process_file(source, db_session, test_user)

        assert log.category == "Documents"
        assert (watch_folder / "Documents" / "notes.txt").exists()


class TestBuildFinalName:
    def test_unchanged_when_timestamp_rename_disabled(self, test_rules, test_engine):
        assert build_final_name("photo.jpg", "Images", test_engine) == "photo.jpg"

    def test_gets_timestamp_prefix_when_enabled_for_category(self, test_rules, test_engine):
        test_rules["enable_timestamp_rename"] = True
        test_rules["timestamp_rename_categories"] = ["Images"]

        name = build_final_name("photo.jpg", "Images", test_engine)

        assert name != "photo.jpg"
        assert name.endswith("_photo.jpg")

    def test_untouched_for_category_not_in_rename_list(self, test_rules, test_engine):
        test_rules["enable_timestamp_rename"] = True
        test_rules["timestamp_rename_categories"] = ["Images"]

        assert build_final_name("notes.txt", "Documents", test_engine) == "notes.txt"


class TestOrganizeExistingFiles:
    def test_organizes_loose_files_in_watch_folder_root(
        self, watch_folder, test_rules, db_session, test_user
    ):
        _write(watch_folder / "notes.txt", "hi")
        _write(watch_folder / "script.py", "print(1)")

        result = organize_existing_files(db_session, test_user)

        assert result == {"scanned": 2, "organized": 2, "duplicates": 0, "errors": 0}
        assert (watch_folder / "Documents" / "notes.txt").exists()
        assert (watch_folder / "Python Projects" / "script.py").exists()

    def test_does_not_descend_into_already_organized_subfolders(
        self, watch_folder, test_rules, db_session, test_user
    ):
        docs = watch_folder / "Documents"
        docs.mkdir()
        _write(docs / "already-there.txt", "hi")

        result = organize_existing_files(db_session, test_user)

        assert result == {"scanned": 0, "organized": 0, "duplicates": 0, "errors": 0}
        assert (docs / "already-there.txt").exists()

    def test_counts_duplicates_separately_from_organized(
        self, watch_folder, test_rules, db_session, test_user
    ):
        docs = watch_folder / "Documents"
        docs.mkdir()
        _write(docs / "notes.txt", "same text")
        _write(watch_folder / "notes.txt", "same text")

        result = organize_existing_files(db_session, test_user)

        assert result == {"scanned": 1, "organized": 0, "duplicates": 1, "errors": 0}

    def test_ignores_partial_download_files(
        self, watch_folder, test_rules, db_session, test_user
    ):
        _write(watch_folder / "movie.mp4.crdownload", "partial")

        result = organize_existing_files(db_session, test_user)

        assert result == {"scanned": 0, "organized": 0, "duplicates": 0, "errors": 0}


class TestUndoLastOperation:
    def test_undo_restores_moved_file(self, watch_folder, test_rules, db_session, test_user):
        source = _write(watch_folder / "notes.txt", "hi")
        process_file(source, db_session, test_user)
        assert not source.exists()

        success, message, log = undo_last_operation(db_session, test_user)

        assert success is True
        assert source.exists()
        assert log.undone is True

    def test_undo_fails_gracefully_with_no_history(self, db_session, test_user):
        success, message, log = undo_last_operation(db_session, test_user)

        assert success is False
        assert log is None

    def test_undo_refuses_to_clobber_a_file_now_at_the_source_path(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "notes.txt", "hi")
        process_file(source, db_session, test_user)
        # something else now occupies the original path
        _write(watch_folder / "notes.txt", "a new unrelated file")

        success, message, log = undo_last_operation(db_session, test_user)

        assert success is False
        assert "already exists" in message

    def test_undo_walks_past_duplicate_skipped_entries_in_history(
        self, watch_folder, test_rules, db_session, test_user
    ):
        first_source = _write(watch_folder / "notes.txt", "same text")
        process_file(first_source, db_session, test_user)
        second_source = _write(watch_folder / "notes.txt", "same text")
        process_file(second_source, db_session, test_user)  # logs duplicate_skipped, left in place

        success, message, log = undo_last_operation(db_session, test_user)

        # undo must skip the duplicate_skipped log entry to find the earlier
        # "moved" one -- it does, but correctly refuses anyway because the
        # duplicate now occupies the original source path.
        assert success is False
        assert "already exists" in message


class TestReclassifyFile:
    def test_moves_the_file_and_logs_a_reclassified_action(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "notes.txt", "hi")
        original_log = process_file(source, db_session, test_user)
        assert original_log.category == "Documents"

        success, message, new_log = reclassify_file(
            original_log.id, "Design", db_session, test_user
        )

        assert success is True
        assert new_log.action == "reclassified"
        assert new_log.category == "Design"
        assert (watch_folder / "Design" / "notes.txt").exists()
        assert not (watch_folder / "Documents" / "notes.txt").exists()
        # the original log entry is untouched -- the reclassify is its own
        # new row, keeping the audit trail intact
        original_log = Document(db_session.activity_log.find_one({"_id": original_log["id"]}))
        assert original_log.action == "moved"
        assert original_log.category == "Documents"

    def test_fails_for_an_entry_with_no_destination_path(
        self, test_rules, db_session, test_user, log_factory
    ):
        log = log_factory(action="duplicate_skipped", destination_path=None)

        success, message, result = reclassify_file(log.id, "Design", db_session, test_user)

        assert success is False
        assert result is None

    def test_fails_when_the_file_no_longer_exists_at_its_logged_location(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "notes.txt", "hi")
        original_log = process_file(source, db_session, test_user)
        (watch_folder / "Documents" / "notes.txt").unlink()

        success, message, result = reclassify_file(
            original_log.id, "Design", db_session, test_user
        )

        assert success is False
        assert "no longer exists" in message

    def test_fails_for_an_already_undone_entry(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "notes.txt", "hi")
        original_log = process_file(source, db_session, test_user)
        undo_last_operation(db_session, test_user)  # marks it undone and moves the file back

        success, message, result = reclassify_file(
            original_log.id, "Design", db_session, test_user
        )

        assert success is False
        assert result is None

    def test_rejects_a_category_that_would_escape_the_watch_folder(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "notes.txt", "hi")
        original_log = process_file(source, db_session, test_user)

        success, message, result = reclassify_file(
            original_log.id, "..\\..\\evil", db_session, test_user
        )

        assert success is False
        assert result is None
        # untouched -- still at its original, valid location
        assert (watch_folder / "Documents" / "notes.txt").exists()

    def test_a_reclassified_entry_is_undoable(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "notes.txt", "hi")
        original_log = process_file(source, db_session, test_user)
        reclassify_file(original_log.id, "Design", db_session, test_user)
        assert (watch_folder / "Design" / "notes.txt").exists()

        success, message, undone_log = undo_last_operation(db_session, test_user)

        assert success is True
        assert undone_log.action == "reclassified"
        assert (watch_folder / "Documents" / "notes.txt").exists()
        assert not (watch_folder / "Design" / "notes.txt").exists()
