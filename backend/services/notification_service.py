import logging

logger = logging.getLogger("fileflow.notifications")


def notify(title: str, message: str, rules: dict) -> None:
    """Best-effort desktop notification. Never lets a notification failure
    break the file organization pipeline (headless/CI environments won't
    have a notification daemon). `rules` is the acting user's own rules
    dict, e.g. RuleEngine.rules."""
    if not rules.get("desktop_notifications_enabled", True):
        return

    try:
        from plyer import notification

        notification.notify(title=title, message=message, timeout=5)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Desktop notification skipped: %s", exc)
