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
