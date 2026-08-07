import threading
from datetime import datetime, timedelta, timezone

from watchdog.observers import Observer

from monitor import watcher
from monitor.watcher import DownloadHandler, _is_inside_managed_subfolder


class ImmediateThread:
    """Stand-in for threading.Thread that runs the target synchronously, so
    tests can assert on _handle()'s gating logic without a real background
    thread and its inherent race between start() and the assertion."""

    def __init__(self, target=None, args=(), daemon=None):
        self._target = target
        self._args = args

    def start(self):
        self._target(*self._args)


class TestIsInsideManagedSubfolder:
    def test_false_for_a_file_loose_in_the_watch_folder_root(self, watch_folder):
        assert _is_inside_managed_subfolder(watch_folder / "report.pdf", watch_folder) is False

    def test_true_for_a_file_already_inside_a_category_folder(self, watch_folder):
        assert (
            _is_inside_managed_subfolder(watch_folder / "Documents" / "report.pdf", watch_folder)
            is True
        )

    def test_false_for_a_path_outside_the_watch_folder(self, watch_folder, tmp_path):
        outside = tmp_path / "elsewhere" / "report.pdf"
        assert _is_inside_managed_subfolder(outside, watch_folder) is False


class TestRealtimeMonitoringGate:
    def test_handle_does_nothing_when_realtime_monitoring_is_disabled(
        self, test_rules, watch_folder, db_session, monkeypatch
    ):
        test_rules["realtime_monitoring_enabled"] = False
        monkeypatch.setattr(watcher.threading, "Thread", ImmediateThread)
        handler = DownloadHandler(
            loop=None, broadcast=None, db=db_session, user_id=1, watch_root=watch_folder
        )
        processed = []
        monkeypatch.setattr(handler, "_process_in_thread", lambda path: processed.append(path))

        handler._handle(watch_folder / "new_download.pdf")

        assert processed == []

    def test_handle_processes_the_file_when_realtime_monitoring_is_enabled(
        self, test_rules, watch_folder, db_session, monkeypatch
    ):
        test_rules["realtime_monitoring_enabled"] = True
        monkeypatch.setattr(watcher.threading, "Thread", ImmediateThread)
        handler = DownloadHandler(
            loop=None, broadcast=None, db=db_session, user_id=1, watch_root=watch_folder
        )
        processed = []
        monkeypatch.setattr(handler, "_process_in_thread", lambda path: processed.append(path))

        target = watch_folder / "new_download.pdf"
        handler._handle(target)

        assert processed == [target]

    def test_handle_ignores_files_already_inside_a_managed_subfolder(
        self, test_rules, watch_folder, db_session, monkeypatch
    ):
        # Enabled, but the file is one FileFlow itself just moved there --
        # re-processing it would be an infinite loop, not a "new download".
        test_rules["realtime_monitoring_enabled"] = True
        monkeypatch.setattr(watcher.threading, "Thread", ImmediateThread)
        handler = DownloadHandler(
            loop=None, broadcast=None, db=db_session, user_id=1, watch_root=watch_folder
        )
        processed = []
        monkeypatch.setattr(handler, "_process_in_thread", lambda path: processed.append(path))

        handler._handle(watch_folder / "Documents" / "already_organized.pdf")

        assert processed == []


class TestAgentConnectedGate:
    """When a remote agent is actively checked in for an account, it's
    already watching this exact folder itself -- the backend's own local
    Observer must step aside so the same file isn't raced by two
    independent watchers (verified directly: without this, a file dropped
    into a same-machine agent's watch folder got "processed" once by each
    side, the loser logging a confusing false duplicate a beat later)."""

    def test_handle_does_nothing_when_a_remote_agent_is_connected(
        self, test_rules, watch_folder, db_session, monkeypatch
    ):
        test_rules["realtime_monitoring_enabled"] = True
        db_session.users.insert_one(
            {"_id": 1, "id": 1, "agent_last_seen_at": datetime.now(timezone.utc)}
        )
        monkeypatch.setattr(watcher.threading, "Thread", ImmediateThread)
        handler = DownloadHandler(
            loop=None, broadcast=None, db=db_session, user_id=1, watch_root=watch_folder
        )
        processed = []
        monkeypatch.setattr(handler, "_process_in_thread", lambda path: processed.append(path))

        handler._handle(watch_folder / "new_download.pdf")

        assert processed == []

    def test_handle_processes_normally_once_the_agent_heartbeat_goes_stale(
        self, test_rules, watch_folder, db_session, monkeypatch
    ):
        test_rules["realtime_monitoring_enabled"] = True
        db_session.users.insert_one(
            {
                "_id": 1,
                "id": 1,
                "agent_last_seen_at": datetime.now(timezone.utc) - timedelta(minutes=10),
            }
        )
        monkeypatch.setattr(watcher.threading, "Thread", ImmediateThread)
        handler = DownloadHandler(
            loop=None, broadcast=None, db=db_session, user_id=1, watch_root=watch_folder
        )
        processed = []
        monkeypatch.setattr(handler, "_process_in_thread", lambda path: processed.append(path))

        target = watch_folder / "new_download.pdf"
        handler._handle(target)

        assert processed == [target]

    def test_handle_processes_normally_when_no_agent_has_ever_connected(
        self, test_rules, watch_folder, db_session, monkeypatch
    ):
        test_rules["realtime_monitoring_enabled"] = True
        db_session.users.insert_one({"_id": 1, "id": 1})
        monkeypatch.setattr(watcher.threading, "Thread", ImmediateThread)
        handler = DownloadHandler(
            loop=None, broadcast=None, db=db_session, user_id=1, watch_root=watch_folder
        )
        processed = []
        monkeypatch.setattr(handler, "_process_in_thread", lambda path: processed.append(path))

        target = watch_folder / "new_download.pdf"
        handler._handle(target)

        assert processed == [target]


class TestScheduleHandlesUnusableFolders:
    """A user's registered watch_folder can go missing on disk between
    registration and now (moved, deleted, external cleanup). _schedule()
    used to let observer.schedule() raise straight out of it, which took
    the entire server down at startup for every user, not just the one
    with the bad path."""

    def _running_observer(self, monkeypatch, db_session):
        observer = Observer()
        monkeypatch.setattr(watcher, "_observer", observer)
        monkeypatch.setattr(watcher, "_loop", None)
        monkeypatch.setattr(watcher, "_broadcast", None)
        monkeypatch.setattr(watcher, "_db", db_session)
        monkeypatch.setattr(watcher, "_watches", {})
        monkeypatch.setattr(watcher, "_primary_folder", {})
        observer.start()
        return observer

    def test_creates_the_watch_folder_if_it_no_longer_exists(self, tmp_path, db_session, monkeypatch):
        observer = self._running_observer(monkeypatch, db_session)
        target = tmp_path / "does_not_exist_yet"
        assert not target.exists()
        try:
            watcher._schedule(1, target)
            assert target.exists()
            assert 1 in watcher._watches
        finally:
            observer.stop()
            observer.join(timeout=2)

    def test_skips_gracefully_when_the_path_cannot_be_created(self, tmp_path, db_session, monkeypatch):
        observer = self._running_observer(monkeypatch, db_session)
        # A file sitting where a directory is expected makes mkdir() raise --
        # a stand-in for any real-world "this path is unusable" case.
        blocker = tmp_path / "blocker_file"
        blocker.write_text("not a directory")
        bad_path = blocker / "subdir"
        try:
            watcher._schedule(1, bad_path)
            assert 1 not in watcher._watches
        finally:
            observer.stop()
            observer.join(timeout=2)

    def test_a_bad_folder_for_one_user_does_not_block_watching_the_next(
        self, tmp_path, db_session, monkeypatch
    ):
        observer = self._running_observer(monkeypatch, db_session)
        blocker = tmp_path / "blocker_file"
        blocker.write_text("not a directory")
        bad_path = blocker / "subdir"
        good_path = tmp_path / "good_user_folder"
        try:
            watcher._schedule(1, bad_path)
            watcher._schedule(2, good_path)

            assert 1 not in watcher._watches
            assert 2 in watcher._watches
            assert good_path.exists()
        finally:
            observer.stop()
            observer.join(timeout=2)


class TestUpdateWatchFolderConcurrency:
    """FastAPI runs each request in its own thread, so a double-submitted
    Settings save (or a slow request plus an impatient retry) can call
    update_watch_folder() for the SAME user from two threads at once.
    Before this was fixed, both threads could read the same stale watch
    object via _watches.get() and both call observer.unschedule() on it --
    the second call raised KeyError straight out of the request handler."""

    def _running_observer(self, monkeypatch, db_session):
        observer = Observer()
        monkeypatch.setattr(watcher, "_observer", observer)
        monkeypatch.setattr(watcher, "_loop", None)
        monkeypatch.setattr(watcher, "_broadcast", None)
        monkeypatch.setattr(watcher, "_db", db_session)
        monkeypatch.setattr(watcher, "_watches", {})
        monkeypatch.setattr(watcher, "_primary_folder", {})
        observer.start()
        return observer

    def test_two_concurrent_updates_for_the_same_user_never_raise(
        self, tmp_path, db_session, monkeypatch
    ):
        observer = self._running_observer(monkeypatch, db_session)
        try:
            initial = tmp_path / "initial"
            watcher._schedule(1, initial)
            watcher._primary_folder[1] = str(initial)

            path_a = tmp_path / "path_a"
            path_b = tmp_path / "path_b"
            errors = []

            def worker(path):
                try:
                    watcher.update_watch_folder(1, path)
                except Exception as exc:  # noqa: BLE001 -- capturing for the assertion below
                    errors.append(exc)

            threads = [
                threading.Thread(target=worker, args=(path_a,)),
                threading.Thread(target=worker, args=(path_b,)),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            assert errors == [], f"update_watch_folder raised under concurrency: {errors}"
            # Whichever request "won" left exactly one consistent watch
            # behind -- not a crash, not a leaked/duplicate entry, and the
            # original "initial" folder (correctly tracked as the primary)
            # was actually replaced rather than left running alongside it.
            assert len(watcher._watches[1]) == 1
        finally:
            observer.stop()
            observer.join(timeout=2)


class TestAdditionalWatchFolders:
    def _running_observer(self, monkeypatch, db_session):
        observer = Observer()
        monkeypatch.setattr(watcher, "_observer", observer)
        monkeypatch.setattr(watcher, "_loop", None)
        monkeypatch.setattr(watcher, "_broadcast", None)
        monkeypatch.setattr(watcher, "_db", db_session)
        monkeypatch.setattr(watcher, "_watches", {})
        monkeypatch.setattr(watcher, "_primary_folder", {})
        observer.start()
        return observer

    def test_an_additional_folder_is_watched_alongside_the_primary(
        self, tmp_path, db_session, monkeypatch
    ):
        observer = self._running_observer(monkeypatch, db_session)
        primary = tmp_path / "primary"
        extra = tmp_path / "extra"
        try:
            watcher.add_user_watch(1, primary)
            watcher.add_additional_watch(1, extra)

            assert str(primary) in watcher._watches[1]
            assert str(extra) in watcher._watches[1]
        finally:
            observer.stop()
            observer.join(timeout=2)

    def test_removing_one_additional_folder_leaves_the_others_running(
        self, tmp_path, db_session, monkeypatch
    ):
        observer = self._running_observer(monkeypatch, db_session)
        primary = tmp_path / "primary"
        extra_a = tmp_path / "extra_a"
        extra_b = tmp_path / "extra_b"
        try:
            watcher.add_user_watch(1, primary)
            watcher.add_additional_watch(1, extra_a)
            watcher.add_additional_watch(1, extra_b)

            watcher.remove_additional_watch(1, extra_a)

            assert str(primary) in watcher._watches[1]
            assert str(extra_a) not in watcher._watches[1]
            assert str(extra_b) in watcher._watches[1]
        finally:
            observer.stop()
            observer.join(timeout=2)

    def test_changing_the_primary_folder_does_not_disturb_additional_folders(
        self, tmp_path, db_session, monkeypatch
    ):
        observer = self._running_observer(monkeypatch, db_session)
        old_primary = tmp_path / "old_primary"
        new_primary = tmp_path / "new_primary"
        extra = tmp_path / "extra"
        try:
            watcher.add_user_watch(1, old_primary)
            watcher.add_additional_watch(1, extra)

            watcher.update_watch_folder(1, new_primary)

            assert str(old_primary) not in watcher._watches[1]
            assert str(new_primary) in watcher._watches[1]
            assert str(extra) in watcher._watches[1]
        finally:
            observer.stop()
            observer.join(timeout=2)

    def test_deleting_the_account_stops_every_folder_primary_and_additional(
        self, tmp_path, db_session, monkeypatch
    ):
        observer = self._running_observer(monkeypatch, db_session)
        primary = tmp_path / "primary"
        extra = tmp_path / "extra"
        try:
            watcher.add_user_watch(1, primary)
            watcher.add_additional_watch(1, extra)

            watcher.remove_user_watch(1)

            assert 1 not in watcher._watches
            assert 1 not in watcher._primary_folder
        finally:
            observer.stop()
            observer.join(timeout=2)

    def test_start_watcher_schedules_additional_folders_from_the_database(
        self, tmp_path, db_session, monkeypatch
    ):
        primary = tmp_path / "primary"
        extra = tmp_path / "extra"
        db_session.users.insert_one(
            {
                "_id": 1,
                "id": 1,
                "email": "multi@example.com",
                "watch_folder": str(primary),
                "additional_watch_folders": [str(extra)],
            }
        )
        monkeypatch.setattr(watcher, "_watches", {})
        monkeypatch.setattr(watcher, "_primary_folder", {})
        observer = watcher.start_watcher(loop=None, broadcast=None, db=db_session)
        try:
            assert str(primary) in watcher._watches[1]
            assert str(extra) in watcher._watches[1]
        finally:
            observer.stop()
            observer.join(timeout=2)
