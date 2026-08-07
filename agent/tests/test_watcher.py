from agent.watcher import AgentDownloadHandler


def _handler():
    return AgentDownloadHandler(client=None, watch_root=None, outbox_conn=None)


def test_not_paused_by_default():
    h = _handler()
    assert h.paused is False


def test_manual_pause_alone_pauses():
    h = _handler()
    h.manually_paused = True
    assert h.paused is True


def test_remote_disable_alone_pauses():
    h = _handler()
    h.remote_monitoring_disabled = True
    assert h.paused is True


def test_both_must_clear_to_resume():
    """The exact scenario the split exists for: pausing from the tray
    while the website's toggle still has monitoring on must not resume
    just because the website says so, and vice versa."""
    h = _handler()
    h.manually_paused = True
    h.remote_monitoring_disabled = True

    h.remote_monitoring_disabled = False
    assert h.paused is True, "Still manually paused -- should stay paused."

    h.manually_paused = False
    assert h.paused is False, "Both cleared -- should resume."
