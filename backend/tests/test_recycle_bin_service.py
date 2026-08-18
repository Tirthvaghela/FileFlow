from datetime import datetime, timedelta, timezone

import pytest
from send2trash import send2trash

from services.recycle_bin_service import (
    _WINSHELL_AVAILABLE,
    purge_all_users_recycle_bins,
    purge_expired_deleted_files,
)

pytestmark = pytest.mark.skipif(
    not _WINSHELL_AVAILABLE, reason="winshell/pywin32 (Recycle Bin access) only available on Windows"
)


class TestRecycleBinPurge:
    def test_purges_an_expired_deleted_file(self, db_session, watch_folder, test_user, log_factory):
        target = watch_folder / "old.txt"
        target.write_text("bye")
        send2trash(str(target))
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=40)
        log_factory(
            action="deleted",
            source_path=str(target),
            destination_path=None,
            file_size=len("bye"),
            timestamp=old_timestamp,
        )

        purged = purge_expired_deleted_files(db_session, test_user)

        assert purged == 1
        row = db_session.activity_log.find_one({"action": "deleted"})
        assert row["recycle_bin_purged"] is True

    def test_does_not_purge_a_deletion_still_within_the_retention_window(
        self, db_session, watch_folder, test_user, log_factory
    ):
        target = watch_folder / "recent.txt"
        target.write_text("keep me for now")
        send2trash(str(target))
        log_factory(action="deleted", source_path=str(target), destination_path=None)

        purged = purge_expired_deleted_files(db_session, test_user)

        assert purged == 0
        row = db_session.activity_log.find_one({"action": "deleted"})
        assert not row.get("recycle_bin_purged")

    def test_respects_a_custom_retention_setting(
        self, db_session, watch_folder, test_user, log_factory, test_rules
    ):
        test_rules["recycle_bin_retention_days"] = 5
        target = watch_folder / "old.txt"
        target.write_text("bye")
        send2trash(str(target))
        log_factory(
            action="deleted",
            source_path=str(target),
            destination_path=None,
            file_size=len("bye"),
            timestamp=datetime.now(timezone.utc) - timedelta(days=6),
        )

        purged = purge_expired_deleted_files(db_session, test_user)

        assert purged == 1

    def test_marks_purged_even_when_already_gone_from_the_recycle_bin(
        self, db_session, watch_folder, test_user, log_factory
    ):
        # Nothing was ever actually sent to the Recycle Bin for this path --
        # simulates the user having already restored it via Explorer, or
        # Windows' own size-based eviction beating this sweep to it.
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=40)
        log_factory(
            action="deleted",
            source_path=str(watch_folder / "never_actually_trashed.txt"),
            destination_path=None,
            timestamp=old_timestamp,
        )

        purged = purge_expired_deleted_files(db_session, test_user)

        assert purged == 0
        row = db_session.activity_log.find_one({"action": "deleted"})
        assert row["recycle_bin_purged"] is True

    def test_never_re_processes_an_already_purged_row(
        self, db_session, watch_folder, test_user, log_factory
    ):
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=40)
        log = log_factory(
            action="deleted",
            source_path=str(watch_folder / "already_done.txt"),
            destination_path=None,
            timestamp=old_timestamp,
        )
        db_session.activity_log.update_one(
            {"_id": log["id"]}, {"$set": {"recycle_bin_purged": True}}
        )

        purged = purge_expired_deleted_files(db_session, test_user)

        assert purged == 0

    def test_sweep_purges_across_every_registered_user(
        self, db_session, watch_folder, log_factory
    ):
        db_session.users.insert_one({"_id": 1, "id": 1, "watch_folder": str(watch_folder)})
        target = watch_folder / "old.txt"
        target.write_text("bye")
        send2trash(str(target))
        log_factory(
            user_id=1,
            action="deleted",
            source_path=str(target),
            destination_path=None,
            file_size=len("bye"),
            timestamp=datetime.now(timezone.utc) - timedelta(days=40),
        )

        total = purge_all_users_recycle_bins(db_session)

        assert total == 1

    def test_sweep_isolates_one_bad_user_from_the_rest(
        self, db_session, watch_folder, monkeypatch
    ):
        import services.recycle_bin_service as svc

        db_session.users.insert_one({"_id": 1, "id": 1, "watch_folder": str(watch_folder)})
        monkeypatch.setattr(
            svc, "purge_expired_deleted_files", lambda db, user: (_ for _ in ()).throw(RuntimeError("boom"))
        )

        total = purge_all_users_recycle_bins(db_session)  # must not raise

        assert total == 0
