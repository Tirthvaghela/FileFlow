from enum import Enum

from config.settings import settings
from models.schemas import WeeklyReportStat
from services.email_service import send_email
from services.stats_service import get_weekly_reports


class DigestOutcome(Enum):
    """What actually happened to one user's weekly digest -- a plain bool
    used to collapse four genuinely different outcomes (sent; nothing to
    report; SMTP not configured at all; a real send failure) into the same
    False value, leaving callers (the scheduler, the manual send-digest
    route) unable to tell an intentional skip from an actual failure."""

    SENT = "sent"
    SKIPPED_NO_ACTIVITY = "skipped_no_activity"
    SKIPPED_SMTP_NOT_CONFIGURED = "skipped_smtp_not_configured"
    FAILED = "failed"


def _format_bytes(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB"):
        if value < 1024:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def build_digest_html(report: WeeklyReportStat) -> str:
    return f"""
    <div style="font-family: sans-serif; max-width: 480px;">
      <h2>FileFlow weekly digest</h2>
      <p style="color: #666;">{report.week_start} to {report.week_end}</p>
      <ul>
        <li><strong>{report.files_organized}</strong> files organized</li>
        <li><strong>{report.duplicates_removed}</strong> duplicates removed</li>
        <li><strong>{_format_bytes(report.storage_optimized_bytes)}</strong> storage optimized</li>
        <li><strong>{report.files_archived}</strong> files archived</li>
      </ul>
    </div>
    """.strip()


def send_weekly_digest(db, user: dict) -> DigestOutcome:
    """Compose and send the most recent 7-day report to one user's own
    registered email. Never raises -- every non-SENT outcome is reported
    back as a specific DigestOutcome instead of a bare False, so callers
    can tell "nothing to report" and "SMTP isn't configured" (both
    intentional, expected skips) apart from an actual send failure."""
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        # Same check send_email() makes internally -- checked here first,
        # before even computing the report, so this specific, expected
        # skip reason is distinguishable from both a real send failure and
        # a zero-activity week without changing send_email()'s own bool
        # contract, which send_password_reset_email() also depends on.
        # Checked ahead of activity: whether SMTP is set up at all is a
        # deployment-level condition independent of any one week's
        # activity, so it's the more useful answer to "why didn't this
        # send" when both are true.
        return DigestOutcome.SKIPPED_SMTP_NOT_CONFIGURED

    reports = get_weekly_reports(db, user["id"], weeks=1)
    if not reports:
        return DigestOutcome.SKIPPED_NO_ACTIVITY

    report = reports[0]
    # get_weekly_reports() always returns exactly one entry for weeks=1
    # (it unconditionally appends once per loop iteration), even when every
    # count is 0 -- `not reports` above can never actually catch a
    # zero-activity week. This is the real check for "nothing to report".
    if not (report.files_organized or report.duplicates_removed or report.files_archived):
        return DigestOutcome.SKIPPED_NO_ACTIVITY

    subject = f"FileFlow weekly digest -- {report.week_start} to {report.week_end}"
    sent = send_email(subject, build_digest_html(report), user["email"])
    return DigestOutcome.SENT if sent else DigestOutcome.FAILED
