import json
import logging
import urllib.error
import urllib.request

from config.settings import settings

logger = logging.getLogger("fileflow.email")

RESEND_API_URL = "https://api.resend.com/emails"


def send_email(subject: str, html: str, to_email: str) -> bool:
    """Best-effort send via the Resend API. Never raises -- a missing key,
    bad credentials, or network failure is logged and swallowed, the same
    pattern notification_service.py uses for external services that must
    never break the caller (here, the scheduled digest job)."""
    if not settings.RESEND_API_KEY:
        logger.info("RESEND_API_KEY not set -- skipping email send.")
        return False

    payload = json.dumps(
        {
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "html": html,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        RESEND_API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
            # Resend sits behind Cloudflare, which blocks urllib's default
            # "Python-urllib/x.y" User-Agent as a bot signature (Cloudflare
            # error 1010) before the request ever reaches Resend's API.
            "User-Agent": "FileFlow/1.0 (+https://github.com)",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status < 400
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        logger.warning("Resend rejected the email (%s): %s", exc.code, body)
        return False
    except urllib.error.URLError as exc:
        logger.warning("Failed to reach Resend: %s", exc)
        return False
