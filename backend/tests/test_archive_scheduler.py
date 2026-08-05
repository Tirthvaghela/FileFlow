import os
import time
from pathlib import Path

import pytest

from scheduler import archive_scheduler
from scheduler.archive_scheduler import archive_old_files


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
