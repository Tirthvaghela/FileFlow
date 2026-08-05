from models.schemas import WeeklyReportStat
from services import digest_service
from services.digest_service import build_digest_html, send_weekly_digest


class TestFormatBytes:
    def test_small_values_stay_in_bytes(self):
        assert digest_service._format_bytes(500) == "500 B"

    def test_scales_up_through_units(self):
        assert digest_service._format_bytes(2048) == "2.0 KB"
        assert digest_service._format_bytes(5 * 1024 * 1024) == "5.0 MB"


class TestBuildDigestHtml:
    def test_includes_all_the_key_numbers_and_date_range(self):
        report = WeeklyReportStat(
            week_start="2026-07-27",
            week_end="2026-08-02",
            files_organized=12,
            duplicates_removed=3,
            storage_optimized_bytes=2048,
            files_archived=1,
        )

        html = build_digest_html(report)

        assert "12" in html
        assert "3" in html
        assert "2.0 KB" in html
        assert "2026-07-27" in html
        assert "2026-08-02" in html


class TestSendWeeklyDigest:
    def test_sends_using_the_most_recent_weeks_report(self, db_session, log_factory, monkeypatch):
        log_factory(action="moved")
        user = {"id": 1, "email": "someone@example.com"}
        captured = {}
        monkeypatch.setattr(
            digest_service,
            "send_email",
            lambda subject, html, to_email: captured.update(
                subject=subject, html=html, to_email=to_email
            )
            or True,
        )

        result = send_weekly_digest(db_session, user)

        assert result is True
        assert "FileFlow weekly digest" in captured["subject"]
        assert captured["to_email"] == "someone@example.com"

    def test_returns_false_when_the_send_itself_fails(self, db_session, monkeypatch):
        monkeypatch.setattr(digest_service, "send_email", lambda *a: False)
        user = {"id": 1, "email": "someone@example.com"}

        assert send_weekly_digest(db_session, user) is False
