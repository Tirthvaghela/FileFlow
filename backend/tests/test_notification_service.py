import plyer

from services import notification_service


def test_skips_the_notification_backend_when_desktop_notifications_disabled(test_rules, monkeypatch):
    test_rules["desktop_notifications_enabled"] = False
    calls = []
    monkeypatch.setattr(plyer.notification, "notify", lambda **kw: calls.append(kw))

    notification_service.notify("Title", "Message", test_rules)

    assert calls == []


def test_calls_the_notification_backend_when_enabled(test_rules, monkeypatch):
    test_rules["desktop_notifications_enabled"] = True
    calls = []
    monkeypatch.setattr(plyer.notification, "notify", lambda **kw: calls.append(kw))

    notification_service.notify("Title", "Message", test_rules)

    assert calls == [{"title": "Title", "message": "Message", "timeout": 5}]


def test_defaults_to_enabled_when_the_field_is_absent(test_rules, monkeypatch):
    assert "desktop_notifications_enabled" not in test_rules
    calls = []
    monkeypatch.setattr(plyer.notification, "notify", lambda **kw: calls.append(kw))

    notification_service.notify("Title", "Message", test_rules)

    assert len(calls) == 1


def test_a_failing_notification_backend_never_raises(test_rules, monkeypatch):
    # Headless/CI machines have no notification daemon -- notify() must be
    # best-effort and never break the file-organization pipeline that calls it.
    test_rules["desktop_notifications_enabled"] = True

    def boom(**kw):
        raise RuntimeError("no notification daemon")

    monkeypatch.setattr(plyer.notification, "notify", boom)

    notification_service.notify("Title", "Message", test_rules)  # must not raise
