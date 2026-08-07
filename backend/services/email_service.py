import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config.settings import settings

logger = logging.getLogger("fileflow.email")


def send_email(subject: str, html: str, to_email: str) -> bool:
    """Best-effort send via SMTP (STARTTLS). Never raises -- missing
    credentials, bad auth, or a network failure is logged and swallowed,
    the same pattern notification_service.py uses for external services
    that must never break the caller (the scheduled digest job, the
    forgot-password endpoint)."""
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        logger.info("SMTP_USERNAME/SMTP_PASSWORD not set -- skipping email send.")
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email
    message.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, [to_email], message.as_string())
        return True
    except smtplib.SMTPException as exc:
        logger.warning("SMTP server rejected the email: %s", exc)
        return False
    except OSError as exc:
        # Connection-level failures (DNS, refused, timeout) -- smtplib lets
        # these surface as plain OSError rather than an SMTPException.
        logger.warning("Failed to reach the SMTP server: %s", exc)
        return False
