import os
import time
from datetime import datetime as real_datetime
from datetime import timezone
from pathlib import Path

import pytest

from scheduler import archive_scheduler
from scheduler.archive_scheduler import archive_old_files, run_scheduled_organizes
from services.storage_threshold_service import check_all_storage_thresholds


class _FrozenClock:
    """Stand-in for the `datetime` class scheduler code calls `.now()` on --
    `.now()` returns a real, fixed datetime so every other method on it
    (`.date()`, `.strftime()`, `.isoformat()`) behaves normally. Avoids
    depending on the real wall clock for a "has this time of day passed
    yet" test, which would otherwise be flaky depending on when tests run."""

    def __init__(self, fixed: real_datetime):
        self._fixed = fixed

    def now(self):
        return self._fixed


@pytest.fixture()
def scheduler_db(db_session, watch_folder, monkeypatch):
    """archive_old_files() writes through the module-level Mongo `db`
    handle rather than taking an injected session -- point that at this
    test's isolated database so it never touches the real production Mongo
    database. It also loops over every registered user, so a single test
    user pointing at the isolated watch_folder is seeded here."""
    monkeypatch.setattr(archive_scheduler, "db", db_session)
    db_session.users.insert_one({"_id": 1, "id": 1, "watch_folder": str(watch_folder)})
    return db_session


def _age(path: Path, days: int) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


class TestArchiveOldFiles:
    def test_moves_files_older_than_the_cutoff(self, test_rules, watch_folder, scheduler_db):
        old_file = watch_folder / "Documents" / "old.pdf"
        old_file.parent.mkdir(parents=True)
        old_file.write_text("hi")
        _age(old_file, days=test_rules["archive_after_days"] + 5)

        count = archive_old_files()

        assert count == 1
        assert not old_file.exists()
        assert (watch_folder / "Archive" / "old.pdf").exists()

    def test_leaves_recently_modified_files_alone(self, test_rules, watch_folder, scheduler_db):
        recent = watch_folder / "Documents" / "recent.pdf"
        recent.parent.mkdir(parents=True)
        recent.write_text("hi")  # freshly written -- well under the cutoff

        count = archive_old_files()

        assert count == 0
        assert recent.exists()

    def test_never_re_archives_files_already_in_the_archive_folder(
        self, test_rules, watch_folder, scheduler_db
    ):
        already = watch_folder / "Archive" / "old.pdf"
        already.parent.mkdir(parents=True)
        already.write_text("hi")
        _age(already, days=test_rules["archive_after_days"] + 5)

        count = archive_old_files()

        assert count == 0

    def test_a_traversal_archive_folder_name_falls_back_to_the_default_instead_of_escaping(
        self, test_rules, watch_folder, scheduler_db
    ):
        # A folder name like this must never send this unattended, scheduled
        # job moving files outside the tree FileFlow was told to manage.
        test_rules["archive_folder"] = "..\\..\\escaped"
        old_file = watch_folder / "Documents" / "old.pdf"
        old_file.parent.mkdir(parents=True)
        old_file.write_text("hi")
        _age(old_file, days=test_rules["archive_after_days"] + 5)

        archive_old_files()

        assert (watch_folder / "Archive" / "old.pdf").exists()
        assert not old_file.exists()
        escaped = (watch_folder / ".." / ".." / "escaped").resolve()
        assert not escaped.exists()

    def test_an_absolute_path_archive_folder_falls_back_to_the_default_instead_of_escaping(
        self, test_rules, watch_folder, tmp_path, scheduler_db
    ):
        outside = tmp_path / "outside_the_watch_folder"
        test_rules["archive_folder"] = str(outside)
        old_file = watch_folder / "Documents" / "old.pdf"
        old_file.parent.mkdir(parents=True)
        old_file.write_text("hi")
        _age(old_file, days=test_rules["archive_after_days"] + 5)

        archive_old_files()

        assert (watch_folder / "Archive" / "old.pdf").exists()
        assert not outside.exists()


class TestScheduledOrganize:
    def test_does_nothing_when_disabled(self, test_rules, watch_folder, scheduler_db, monkeypatch):
        test_rules["scheduled_organize_enabled"] = False
        test_rules["scheduled_organize_time"] = "00:00"
        monkeypatch.setattr(archive_scheduler, "datetime", _FrozenClock(real_datetime(2026, 1, 1, 3, 0)))
        loose = watch_folder / "report.pdf"
        loose.write_text("hi")

        run_scheduled_organizes()

        assert loose.exists()

    def test_does_nothing_before_the_configured_time(
        self, test_rules, watch_folder, scheduler_db, monkeypatch
    ):
        test_rules["scheduled_organize_enabled"] = True
        test_rules["scheduled_organize_time"] = "23:59"
        monkeypatch.setattr(archive_scheduler, "datetime", _FrozenClock(real_datetime(2026, 1, 1, 3, 0)))
        loose = watch_folder / "report.pdf"
        loose.write_text("hi")

        run_scheduled_organizes()

        assert loose.exists()

    def test_organizes_once_the_configured_time_has_passed(
        self, test_rules, watch_folder, scheduler_db, monkeypatch
    ):
        test_rules["scheduled_organize_enabled"] = True
        test_rules["scheduled_organize_time"] = "02:00"
        monkeypatch.setattr(archive_scheduler, "datetime", _FrozenClock(real_datetime(2026, 1, 1, 3, 0)))
        loose = watch_folder / "report.pdf"
        loose.write_text("hi")

        run_scheduled_organizes()

        assert not loose.exists()
        assert (watch_folder / "Documents" / "report.pdf").exists()

    def test_does_not_run_twice_in_the_same_day(
        self, test_rules, watch_folder, scheduler_db, monkeypatch
    ):
        test_rules["scheduled_organize_enabled"] = True
        test_rules["scheduled_organize_time"] = "02:00"
        monkeypatch.setattr(archive_scheduler, "datetime", _FrozenClock(real_datetime(2026, 1, 1, 3, 0)))
        first = watch_folder / "first.pdf"
        first.write_text("hi")
        run_scheduled_organizes()
        assert not first.exists()

        # A second file drops later the same day (still past 2am) -- the
        # sweep already ran once today and must not fire again until
        # tomorrow, matching "Organize existing files now" being a
        # one-shot action rather than continuous polling.
        second = watch_folder / "second.pdf"
        second.write_text("hi")
        run_scheduled_organizes()

        assert second.exists()

    def test_runs_again_the_next_day(self, test_rules, watch_folder, scheduler_db, monkeypatch):
        test_rules["scheduled_organize_enabled"] = True
        test_rules["scheduled_organize_time"] = "02:00"
        monkeypatch.setattr(archive_scheduler, "datetime", _FrozenClock(real_datetime(2026, 1, 1, 3, 0)))
        first = watch_folder / "first.pdf"
        first.write_text("hi")
        run_scheduled_organizes()

        monkeypatch.setattr(archive_scheduler, "datetime", _FrozenClock(real_datetime(2026, 1, 2, 3, 0)))
        second = watch_folder / "second.pdf"
        second.write_text("hi")
        run_scheduled_organizes()

        assert not second.exists()
        assert (watch_folder / "Documents" / "second.pdf").exists()

    def test_dispatches_to_the_agent_instead_of_running_locally_when_connected(
        self, test_rules, watch_folder, scheduler_db, monkeypatch
    ):
        test_rules["scheduled_organize_enabled"] = True
        test_rules["scheduled_organize_time"] = "02:00"
        monkeypatch.setattr(archive_scheduler, "datetime", _FrozenClock(real_datetime(2026, 1, 1, 3, 0)))
        # is_agent_connected() checks the real wall clock (it's in a
        # different module than the frozen one above), so this needs to be
        # a genuinely recent, real UTC timestamp -- not tied to the frozen
        # 2026-01-01 date used for the scheduled-time comparison.
        scheduler_db.users.update_one(
            {"_id": 1}, {"$set": {"agent_last_seen_at": real_datetime.now(timezone.utc)}}
        )
        loose = watch_folder / "report.pdf"
        loose.write_text("hi")

        run_scheduled_organizes()

        # Left for the agent to actually move -- the backend must not also
        # touch the file itself when an agent is connected for this account.
        assert loose.exists()
        command = scheduler_db.agent_commands.find_one({"user_id": 1, "type": "organize_existing"})
        assert command is not None
        assert command["status"] == "pending"

    def test_direct_organize_logs_the_actual_counts_not_just_that_it_ran(
        self, test_rules, watch_folder, scheduler_db, monkeypatch, caplog
    ):
        """Regression test for a real, confirmed observability gap:
        organize_existing_files()'s return value (scanned/organized/
        duplicates/errors) was previously discarded here entirely --
        unlike archive_old_files() in this same module, which already logs
        its own count. Without this, "Job 'run_scheduled_organizes'
        executed successfully" in the log is indistinguishable from an
        actual "organized 3 files" outcome -- exactly the gap that made
        the original symptom this task investigates hard to diagnose from
        logs alone."""
        test_rules["scheduled_organize_enabled"] = True
        test_rules["scheduled_organize_time"] = "02:00"
        monkeypatch.setattr(archive_scheduler, "datetime", _FrozenClock(real_datetime(2026, 1, 1, 3, 0)))
        loose = watch_folder / "report.pdf"
        loose.write_text("hi")

        import logging

        with caplog.at_level(logging.INFO, logger="fileflow.archive"):
            run_scheduled_organizes()

        assert not loose.exists()
        messages = [r.message for r in caplog.records if r.name == "fileflow.archive"]
        assert any("scanned 1" in m and "organized 1" in m for m in messages), (
            f"expected the real organize counts to be logged, got: {messages}"
        )

    def test_dispatch_to_agent_is_also_logged(
        self, test_rules, watch_folder, scheduler_db, monkeypatch, caplog
    ):
        test_rules["scheduled_organize_enabled"] = True
        test_rules["scheduled_organize_time"] = "02:00"
        monkeypatch.setattr(archive_scheduler, "datetime", _FrozenClock(real_datetime(2026, 1, 1, 3, 0)))
        scheduler_db.users.update_one(
            {"_id": 1}, {"$set": {"agent_last_seen_at": real_datetime.now(timezone.utc)}}
        )

        import logging

        with caplog.at_level(logging.INFO, logger="fileflow.archive"):
            run_scheduled_organizes()

        messages = [r.message for r in caplog.records if r.name == "fileflow.archive"]
        assert any("dispatched to agent" in m for m in messages), (
            f"expected the agent dispatch to be logged, got: {messages}"
        )


class TestStorageThreshold:
    def test_does_nothing_when_no_threshold_configured(self, test_rules, watch_folder, scheduler_db):
        f = watch_folder / "Documents" / "small.pdf"
        f.parent.mkdir(parents=True)
        f.write_text("hi")

        check_all_storage_thresholds(scheduler_db)

        assert f.exists()
        assert scheduler_db.activity_log.count_documents({"action": "archived"}) == 0

    def test_does_nothing_below_threshold(self, test_rules, watch_folder, scheduler_db):
        test_rules["storage_alert_threshold_gb"] = 1
        f = watch_folder / "Documents" / "small.pdf"
        f.parent.mkdir(parents=True)
        f.write_text("hi")

        check_all_storage_thresholds(scheduler_db)

        assert f.exists()
        assert scheduler_db.activity_log.count_documents({"action": "archived"}) == 0

    def test_archives_only_the_oldest_file_needed_to_drop_back_under_threshold(
        self, test_rules, watch_folder, scheduler_db
    ):
        folder = watch_folder / "Documents"
        folder.mkdir(parents=True)
        old = folder / "old.pdf"
        old.write_text("a" * 1000)
        _age(old, days=10)
        newer = folder / "newer.pdf"
        newer.write_text("a" * 1000)
        _age(newer, days=1)
        test_rules["storage_alert_threshold_gb"] = 1500 / (1024**3)

        check_all_storage_thresholds(scheduler_db)

        assert not old.exists()
        assert (watch_folder / "Archive" / "old.pdf").exists()
        assert newer.exists()
        log = scheduler_db.activity_log.find_one({"action": "archived"})
        assert log["original_filename"] == "old.pdf"

    def test_skips_the_configured_archive_folder_itself(self, test_rules, watch_folder, scheduler_db):
        test_rules["storage_alert_threshold_gb"] = 1000 / (1024**3)
        archive = watch_folder / "Archive"
        archive.mkdir(parents=True)
        (archive / "already_archived.pdf").write_text("a" * 2000)

        check_all_storage_thresholds(scheduler_db)

        assert (archive / "already_archived.pdf").exists()
        assert scheduler_db.activity_log.count_documents({"action": "archived"}) == 0

    def test_sends_a_notification_describing_what_happened(
        self, test_rules, watch_folder, scheduler_db, monkeypatch
    ):
        import services.storage_threshold_service as svc

        calls = []
        monkeypatch.setattr(svc, "notify", lambda title, message, rules: calls.append(message))
        folder = watch_folder / "Documents"
        folder.mkdir(parents=True)
        (folder / "big.pdf").write_text("a" * 2000)
        test_rules["storage_alert_threshold_gb"] = 1000 / (1024**3)

        check_all_storage_thresholds(scheduler_db)

        assert len(calls) == 1
        assert "Documents" in calls[0]
