from models.schemas import WeeklyReportStat
from services.email_service import send_email
from services.stats_service import get_weekly_reports


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


def send_weekly_digest(db, user: dict) -> bool:
    """Compose and send the most recent 7-day report to one user's own
    registered email. Returns False (never raises) if there's nothing to
    report or the send itself fails -- see email_service.send_email for
    the delivery contract."""
    reports = get_weekly_reports(db, user["id"], weeks=1)
    if not reports:
        return False

    report = reports[0]
    subject = f"FileFlow weekly digest -- {report.week_start} to {report.week_end}"
    return send_email(subject, build_digest_html(report), user["email"])
