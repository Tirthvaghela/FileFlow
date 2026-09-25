import threading
from pathlib import Path

from automation import organizer
from automation.organizer import (
    build_final_name,
    compute_hash,
    organize_existing_files,
    plan_organize_existing,
    process_file,
    reclassify_file,
    resolve_destination,
    undo_last_operation,
    wait_for_stable_file,
)
from config.settings import settings
from models.models import Document


def _write(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


class TestWaitForStableFile:
    def test_true_once_size_stops_changing_between_polls(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "STABILITY_POLL_INTERVAL", 0.01)
        monkeypatch.setattr(settings, "STABILITY_TIMEOUT", 1.0)
        path = _write(tmp_path / "steady.txt", "hello")

        assert wait_for_stable_file(path) is True

    def test_false_when_the_file_never_existed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "STABILITY_POLL_INTERVAL", 0.01)
        monkeypatch.setattr(settings, "STABILITY_TIMEOUT", 0.05)

        assert wait_for_stable_file(tmp_path / "never_created.txt") is False

    def test_false_for_a_file_still_growing_on_every_poll_at_the_timeout(self, tmp_path, monkeypatch):
        # A file that changes size on every single poll (e.g. a slow trickle
        # download) must NOT be treated as "stable" just because it's still
        # sitting there when the timeout hits -- that would mean moving and
        # hashing a file that's still being written to.
        monkeypatch.setattr(settings, "STABILITY_POLL_INTERVAL", 0.01)
        monkeypatch.setattr(settings, "STABILITY_TIMEOUT", 0.05)
        path = _write(tmp_path / "growing.txt", "x")

        # pathlib.Path uses __slots__, so instance-level patching isn't
        # possible -- patch the class method but pass every other path
        # (including pytest's own internal Path.stat() calls) straight
        # through to the real implementation untouched.
        original_stat = Path.stat
        sizes = iter(range(1, 1000))

        def fake_stat(self, *args, **kwargs):
            if self == path:
                return type("FakeStat", (), {"st_size": next(sizes)})()
            return original_stat(self, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", fake_stat)

        assert wait_for_stable_file(path) is False


class TestResolveDestination:
    def test_returns_moved_when_destination_is_free(self, tmp_path, test_engine):
        dest_folder = tmp_path / "Documents"
        dest_folder.mkdir()
        source = _write(tmp_path / "a.txt", "hello")

        dest_path, action = resolve_destination(dest_folder, "a.txt", source, test_engine.rules)

        assert action == "moved"
        assert dest_path == dest_folder / "a.txt"

    def test_returns_duplicate_skipped_when_content_matches(self, tmp_path, test_engine):
        dest_folder = tmp_path / "Documents"
        dest_folder.mkdir()
        _write(dest_folder / "a.txt", "hello")
        source = _write(tmp_path / "a.txt", "hello")

        dest_path, action = resolve_destination(dest_folder, "a.txt", source, test_engine.rules)

        assert action == "duplicate_skipped"
        assert dest_path is None

    def test_renames_with_counter_when_content_differs(self, tmp_path, test_engine):
        dest_folder = tmp_path / "Documents"
        dest_folder.mkdir()
        _write(dest_folder / "a.txt", "existing content")
        source = _write(tmp_path / "a.txt", "different content")

        dest_path, action = resolve_destination(dest_folder, "a.txt", source, test_engine.rules)

        assert action == "renamed_and_moved"
        assert dest_path == dest_folder / "a (1).txt"

    def test_renames_skip_taken_counters(self, tmp_path, test_engine):
        dest_folder = tmp_path / "Documents"
        dest_folder.mkdir()
        _write(dest_folder / "a.txt", "existing")
        _write(dest_folder / "a (1).txt", "existing-1")
        source = _write(tmp_path / "a.txt", "new content")

        dest_path, action = resolve_destination(dest_folder, "a.txt", source, test_engine.rules)

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

    def test_activity_log_carries_the_explanation_that_actually_decided_the_destination(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "Invoice_March.pdf", "invoice contents")

        log = process_file(source, db_session, test_user)

        assert log.explanation["match_type"] == "keyword"
        assert log.explanation["matched_value"] == "invoice"
        # Must never disagree with the actual destination the file landed in.
        assert log.explanation["destination"] == log.category == "Finance Folder"
        row = Document(db_session.activity_log.find_one({"_id": log.id}))
        assert row.explanation == log.explanation

    def test_duplicate_skipped_entries_also_carry_an_explanation(
        self, watch_folder, test_rules, db_session, test_user
    ):
        _write(watch_folder / "notes.txt", "same content")
        process_file(watch_folder / "notes.txt", db_session, test_user)
        _write(watch_folder / "notes.txt", "same content")

        log = process_file(watch_folder / "notes.txt", db_session, test_user)

        assert log.action == "duplicate_skipped"
        assert log.explanation is not None
        assert log.explanation["destination"] == log.category

    def test_a_file_with_no_matching_rule_gets_a_default_explanation(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "mystery.xyz123", "??")
        test_rules["auto_organize_unknown_extensions"] = False

        log = process_file(source, db_session, test_user)

        assert log.category == "Others"
        assert log.explanation["match_type"] == "default"
        assert log.explanation["matched_value"] is None
        assert log.explanation["rule_name"] is None


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

    def test_does_not_crash_when_uipath_actually_moved_the_file_but_reports_none(
        self, watch_folder, test_rules, db_session, test_user, monkeypatch
    ):
        # A Robot can genuinely complete the physical move and then still
        # cause execute_move_via_uipath() to return None -- e.g. a non-zero
        # exit code from some unrelated post-move step, or output Python
        # can't parse. Simulate exactly that: the fake mover performs the
        # real move (like a Robot that actually succeeded) but reports
        # failure the same way those code paths do, by returning None
        # without ever checking the filesystem itself.
        def fake_uipath_lies_about_failure(source, dest_folder, final_name):
            dest_folder.mkdir(parents=True, exist_ok=True)
            source.rename(dest_folder / final_name)
            return None

        monkeypatch.setattr(organizer, "execute_move_via_uipath", fake_uipath_lies_about_failure)
        source = _write(watch_folder / "notes.txt", "hi")

        log = process_file(source, db_session, test_user)

        # Must not have raised trying to rename an already-gone source, and
        # the operation must still be logged/undoable -- not silently lost
        # just because the Robot's own status report was unreliable.
        assert log is not None
        assert log.category == "Documents"
        assert (watch_folder / "Documents" / "notes.txt").exists()
        assert not source.exists()

    def test_a_file_in_an_additional_watch_folder_is_routed_to_uipath_with_that_folders_own_path(
        self, tmp_path, watch_folder, test_rules, db_session, test_user, monkeypatch
    ):
        """execute_move_via_uipath() has no folder-selection logic of its
        own -- it just receives whatever dest_folder the caller already
        resolved (confirmed by reading uipath_service.py: it takes plain
        Path arguments, never a user dict or all_watch_folders() call).
        Multi-folder correctness for the UiPath path is therefore entirely
        inherited from organize_existing_files()'s own per-folder
        substitution (already audited and fixed for reclassify_file() in
        an earlier task) -- this confirms that inheritance actually holds:
        a file in an *additional* folder must reach UiPath with THAT
        folder's own dest_folder, never the primary watch_folder."""
        additional = tmp_path / "additional_watch"
        additional.mkdir()
        user = {**test_user, "additional_watch_folders": [str(additional)]}
        _write(additional / "notes.txt", "hi")

        captured = {}

        def fake_uipath(source, dest_folder, final_name):
            captured["dest_folder"] = dest_folder
            dest_folder.mkdir(parents=True, exist_ok=True)
            source.rename(dest_folder / final_name)
            return dest_folder / final_name

        monkeypatch.setattr(organizer, "execute_move_via_uipath", fake_uipath)

        result = organize_existing_files(db_session, user)

        assert result["organized"] == 1
        assert captured["dest_folder"] == additional / "Documents", (
            "UiPath must be asked to move the file within its OWN watch folder, "
            "not the account's primary one"
        )
        assert (additional / "Documents" / "notes.txt").exists()
        assert not (watch_folder / "Documents" / "notes.txt").exists()


class TestBuildFinalName:
    def test_unchanged_when_timestamp_rename_disabled(self, test_rules, test_engine):
        assert build_final_name("photo.jpg", "Images", test_engine.rules) == "photo.jpg"

    def test_gets_timestamp_prefix_when_enabled_for_category(self, test_rules, test_engine):
        test_rules["enable_timestamp_rename"] = True
        test_rules["timestamp_rename_categories"] = ["Images"]

        name = build_final_name("photo.jpg", "Images", test_engine.rules)

        assert name != "photo.jpg"
        assert name.endswith("_photo.jpg")

    def test_untouched_for_category_not_in_rename_list(self, test_rules, test_engine):
        test_rules["enable_timestamp_rename"] = True
        test_rules["timestamp_rename_categories"] = ["Images"]

        assert build_final_name("notes.txt", "Documents", test_engine.rules) == "notes.txt"


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

    def test_two_concurrent_undo_calls_never_raise_and_only_one_succeeds(
        self, watch_folder, test_rules, db_session, test_user
    ):
        # A double-click, or a slow request plus an impatient retry, used
        # to let both calls read the same undone=False row, both pass the
        # exists() checks, and race shutil.move() on the same file -- the
        # loser raised straight out of the function as an unhandled 500.
        source = _write(watch_folder / "notes.txt", "hi")
        process_file(source, db_session, test_user)

        results = []
        errors = []

        def worker():
            try:
                results.append(undo_last_operation(db_session, test_user))
            except Exception as exc:  # noqa: BLE001 -- captured for the assertion below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == [], f"undo_last_operation raised under concurrency: {errors}"
        successes = [r for r in results if r[0] is True]
        assert len(successes) == 1
        assert Path(watch_folder / "notes.txt").exists()

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

    def test_a_manual_reclassify_carries_no_explanation(
        self, watch_folder, test_rules, db_session, test_user
    ):
        # No rule was evaluated here at all -- the user picked "Design"
        # themselves. Attributing this to a rule would be a fabricated
        # explanation, so the reclassified row must simply have none.
        source = _write(watch_folder / "notes.txt", "hi")
        original_log = process_file(source, db_session, test_user)
        assert original_log.explanation is not None

        success, message, new_log = reclassify_file(
            original_log.id, "Design", db_session, test_user
        )

        assert success is True
        assert new_log.get("explanation") is None

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

    def test_two_concurrent_reclassify_calls_for_the_same_entry_never_raise(
        self, watch_folder, test_rules, db_session, test_user
    ):
        # Same class of race as undo: two calls reclassifying the same
        # log_id at once used to both pass the source.exists() check and
        # race shutil.move() on the same file -- the loser raised an
        # unhandled OSError instead of a graceful failure response.
        source = _write(watch_folder / "notes.txt", "hi")
        original_log = process_file(source, db_session, test_user)

        results = []
        errors = []

        def worker():
            try:
                results.append(
                    reclassify_file(original_log.id, "Design", db_session, test_user)
                )
            except Exception as exc:  # noqa: BLE001 -- captured for the assertion below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == [], f"reclassify_file raised under concurrency: {errors}"
        successes = [r for r in results if r[0] is True]
        assert len(successes) == 1
        assert (watch_folder / "Design" / "notes.txt").exists()

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

    def test_reclassify_keeps_a_file_in_its_own_additional_watch_folder(
        self, tmp_path, watch_folder, test_rules, db_session, test_user
    ):
        """Regression test for a real, confirmed bug: reclassify_file()
        always computed its destination relative to Path(user["watch_
        folder"]) -- the account's PRIMARY folder only -- never checking
        which watch folder the file actually lives in. organize_existing_
        files() already gets this right (it substitutes the correct
        watch_root per file, see its own docstring/comment), so a file
        organized into an *additional* folder's own category subfolder
        genuinely exists on disk -- reclassifying it silently relocated it
        into the PRIMARY folder's category subfolder instead of staying
        within the additional folder it actually came from (a same-drive
        rename doesn't even raise; it just silently moves the file into
        the wrong top-level watch folder)."""
        additional = tmp_path / "additional_watch"
        additional.mkdir()
        user = {**test_user, "additional_watch_folders": [str(additional)]}

        source = _write(additional / "notes.txt", "hi")
        original_log = organize_existing_files(db_session, user)
        assert original_log["organized"] == 1
        assert (additional / "Documents" / "notes.txt").exists()

        log_row = db_session.activity_log.find_one({"user_id": user["id"], "action": "moved"})

        success, message, new_log = reclassify_file(log_row["id"], "Design", db_session, user)

        assert success is True, message
        assert (additional / "Design" / "notes.txt").exists(), (
            "a file organized into an additional watch folder must be reclassified "
            "within that SAME folder, not relocated into the primary watch folder"
        )
        assert not (watch_folder / "Design" / "notes.txt").exists(), (
            "reclassify must never move a file into a different top-level watch "
            "folder than the one it actually came from"
        )


class TestPlanOrganizeExisting:
    """plan_organize_existing() -- the read-only dry run behind the
    Organization Preview feature. Must discover the same files
    organize_existing_files() would and plan the exact same decision via
    the shared plan_file_organization() (automation/file_ops.py), without
    ever touching the filesystem beyond reads."""

    def test_returns_the_correct_planned_destination(
        self, watch_folder, test_rules, db_session, test_user
    ):
        _write(watch_folder / "Invoice_March.pdf", "invoice contents")

        items = plan_organize_existing(db_session, test_user)

        assert len(items) == 1
        assert items[0]["filename"] == "Invoice_March.pdf"
        assert items[0]["category"] == "Finance Folder"
        assert items[0]["destination_path"] == str(
            watch_folder / "Finance Folder" / "Invoice_March.pdf"
        )
        assert items[0]["status"] == "ready"

    def test_uses_the_real_classifier_and_carries_the_real_explanation(
        self, watch_folder, test_rules, db_session, test_user
    ):
        _write(watch_folder / "Invoice_March.pdf", "invoice contents")

        items = plan_organize_existing(db_session, test_user)

        explanation = items[0]["explanation"]
        assert explanation["match_type"] == "keyword"
        assert explanation["matched_value"] == "invoice"
        # Must never disagree with the item's own planned destination.
        assert explanation["destination"] == items[0]["category"] == "Finance Folder"

    def test_never_moves_renames_or_deletes_anything(
        self, watch_folder, test_rules, db_session, test_user
    ):
        source = _write(watch_folder / "notes.txt", "hi")
        before = source.stat().st_mtime

        plan_organize_existing(db_session, test_user)

        assert source.exists(), "the source file must still be exactly where it was"
        assert source.read_text() == "hi"
        assert source.stat().st_mtime == before
        assert not (watch_folder / "Documents").exists(), (
            "preview must never even create the destination folder"
        )

    def test_creates_no_activity_log_rows(self, watch_folder, test_rules, db_session, test_user):
        _write(watch_folder / "notes.txt", "hi")
        _write(watch_folder / "report.pdf", "pdf contents")

        plan_organize_existing(db_session, test_user)

        assert db_session.activity_log.count_documents({}) == 0

    def test_no_matching_rule_is_flagged_no_match_not_a_fabricated_rule(
        self, watch_folder, test_rules, db_session, test_user
    ):
        _write(watch_folder / "mystery.xyz123", "??")
        test_rules["auto_organize_unknown_extensions"] = False

        items = plan_organize_existing(db_session, test_user)

        assert items[0]["status"] == "no_match"
        assert items[0]["explanation"]["match_type"] == "default"
        assert items[0]["explanation"]["rule_name"] is None

    def test_a_duplicate_is_flagged_and_still_carries_its_explanation(
        self, watch_folder, test_rules, db_session, test_user
    ):
        dest = watch_folder / "Documents"
        dest.mkdir()
        _write(dest / "notes.txt", "same content")
        _write(watch_folder / "notes.txt", "same content")

        items = plan_organize_existing(db_session, test_user)

        assert items[0]["status"] == "duplicate"
        assert items[0]["action"] == "duplicate_skipped"
        assert items[0]["explanation"] is not None

    def test_a_genuine_name_collision_with_different_content_is_previewed_as_a_rename(
        self, watch_folder, test_rules, db_session, test_user
    ):
        # Same collision-handling resolve_destination() already applies for
        # real ("rename" mode, different content -> " (1)" suffix) -- the
        # preview must show that exact same planned outcome, not a
        # different, preview-only conflict policy.
        dest = watch_folder / "Documents"
        dest.mkdir()
        (dest / "notes.txt").write_text("original content")
        _write(watch_folder / "notes.txt", "different content")

        items = plan_organize_existing(db_session, test_user)

        assert items[0]["action"] == "renamed_and_moved"
        assert items[0]["status"] == "ready"
        assert items[0]["destination_path"] == str(dest / "notes (1).txt")

    def test_multiple_files_produce_independent_results(
        self, watch_folder, test_rules, db_session, test_user
    ):
        _write(watch_folder / "Invoice_March.pdf", "invoice contents")
        _write(watch_folder / "script.py", "print('hi')")
        _write(watch_folder / "photo.jpg", "img")

        items = plan_organize_existing(db_session, test_user)

        by_name = {i["filename"]: i for i in items}
        assert by_name["Invoice_March.pdf"]["category"] == "Finance Folder"
        assert by_name["script.py"]["category"] == "Python Projects"
        assert by_name["photo.jpg"]["category"] == "Images"

    def test_one_unreadable_file_does_not_abort_the_rest_of_the_preview(
        self, watch_folder, test_rules, db_session, test_user, monkeypatch
    ):
        _write(watch_folder / "good.pdf", "pdf contents")
        broken = _write(watch_folder / "broken.pdf", "pdf contents")

        real_plan = organizer.plan_file_organization

        def _flaky(source_path, *args, **kwargs):
            if source_path.name == "broken.pdf":
                raise OSError("simulated unreadable file")
            return real_plan(source_path, *args, **kwargs)

        monkeypatch.setattr(organizer, "plan_file_organization", _flaky)

        items = plan_organize_existing(db_session, test_user)

        by_name = {i["filename"]: i for i in items}
        assert by_name["good.pdf"]["status"] == "ready"
        assert by_name["broken.pdf"]["status"] == "error"
        assert by_name["broken.pdf"]["explanation"] is None
        # A safe message, never a raw exception/traceback.
        assert "simulated unreadable file" not in by_name["broken.pdf"]["error"]

    def test_rule_priority_is_preserved_over_a_weaker_match(
        self, watch_folder, test_rules, db_session, test_user
    ):
        # "Invoice_March.pdf" would map to Documents by extension/category
        # alone -- the keyword rule (priority 1) must still win in preview,
        # exactly as it does for the real operation.
        _write(watch_folder / "Invoice_March.pdf", "invoice contents")

        items = plan_organize_existing(db_session, test_user)

        assert items[0]["category"] == "Finance Folder"
        assert items[0]["explanation"]["priority"] == 1

    def test_sweeps_additional_watch_folders_too(
        self, watch_folder, test_rules, db_session, test_user, tmp_path
    ):
        extra = tmp_path / "extra_watch_folder"
        extra.mkdir()
        user = {**test_user, "additional_watch_folders": [str(extra)]}
        _write(watch_folder / "notes.txt", "hi")
        _write(extra / "script.py", "print(1)")

        items = plan_organize_existing(db_session, user)

        by_name = {i["filename"]: i for i in items}
        assert by_name["notes.txt"]["destination_path"] == str(
            watch_folder / "Documents" / "notes.txt"
        )
        assert by_name["script.py"]["destination_path"] == str(
            extra / "Python Projects" / "script.py"
        )

    def test_already_organized_files_are_not_rescanned(
        self, watch_folder, test_rules, db_session, test_user
    ):
        already = watch_folder / "Documents" / "already_organized.pdf"
        already.parent.mkdir(parents=True)
        already.write_text("hi")

        items = plan_organize_existing(db_session, test_user)

        assert items == []
