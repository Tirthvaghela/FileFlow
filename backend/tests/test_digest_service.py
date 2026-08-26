from config.settings import settings
from models.schemas import WeeklyReportStat
from services import digest_service
from services.digest_service import DigestOutcome, build_digest_html, send_weekly_digest


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


# ---------------------------------------------------------------------------
# send_weekly_digest() -- every test here explicitly monkeypatches SMTP_
# USERNAME/SMTP_PASSWORD to fake values (never the real ones this
# environment's own .env may configure) so each test's outcome is
# deterministic and never depends on -- or risks touching -- real SMTP
# credentials. send_email() itself is always mocked too, so no real
# network call or email send is ever reachable from these tests.
# ---------------------------------------------------------------------------


def _configure_fake_smtp(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_USERNAME", "fake@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "fake-app-password")


class TestSendWeeklyDigest:
    def test_sends_using_the_most_recent_weeks_report(self, db_session, log_factory, monkeypatch):
        _configure_fake_smtp(monkeypatch)
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

        assert result is DigestOutcome.SENT
        assert "FileFlow weekly digest" in captured["subject"]
        assert captured["to_email"] == "someone@example.com"

    def test_reports_failed_when_the_send_itself_fails(self, db_session, log_factory, monkeypatch):
        _configure_fake_smtp(monkeypatch)
        log_factory(action="moved")  # real activity -- must reach send_email, not skip beforehand
        monkeypatch.setattr(digest_service, "send_email", lambda *a: False)
        user = {"id": 1, "email": "someone@example.com"}

        assert send_weekly_digest(db_session, user) is DigestOutcome.FAILED

    def test_skips_with_no_activity_when_the_user_had_zero_activity_this_week(
        self, db_session, monkeypatch
    ):
        """Regression test for a real, confirmed bug: send_weekly_digest()'s
        own docstring says it "Returns False... if there's nothing to
        report", implemented as `if not reports: return False` -- but
        get_weekly_reports(db, user_id, weeks=1) unconditionally appends
        exactly one WeeklyReportStat per iteration of its `for _ in
        range(weeks):` loop, with every field defaulting to 0 when no
        matching activity_log documents exist. With `weeks=1`, `reports`
        is therefore NEVER empty -- confirmed directly: a fresh account
        with zero activity_log entries still gets a real WeeklyReportStat
        with every count at 0, so `not reports` never fires and a
        zero-activity user was sent a "0 files organized, 0 duplicates,
        0 archived" email every week regardless. Now reported as the
        specific SKIPPED_NO_ACTIVITY outcome rather than a bare False."""
        _configure_fake_smtp(monkeypatch)
        sent = []
        monkeypatch.setattr(digest_service, "send_email", lambda *a: sent.append(a) or True)
        user = {"id": 1, "email": "someone@example.com"}  # no activity_log rows at all

        result = send_weekly_digest(db_session, user)

        assert result is DigestOutcome.SKIPPED_NO_ACTIVITY
        assert sent == [], "send_email must never be called for a zero-activity report"

    def test_skips_with_smtp_not_configured_ahead_of_the_activity_check(
        self, db_session, log_factory, monkeypatch
    ):
        """SMTP-not-configured is checked (and reported) before the
        activity check, even when there IS real activity to report --
        it's a deployment-level condition independent of any one week's
        data, and the more useful answer to "why didn't this send" when
        both conditions happen to be true."""
        monkeypatch.setattr(settings, "SMTP_USERNAME", None)
        monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
        log_factory(action="moved")  # real activity exists -- must not matter here
        sent = []
        monkeypatch.setattr(digest_service, "send_email", lambda *a: sent.append(a) or True)
        user = {"id": 1, "email": "someone@example.com"}

        result = send_weekly_digest(db_session, user)

        assert result is DigestOutcome.SKIPPED_SMTP_NOT_CONFIGURED
        assert sent == [], "send_email must never be called when SMTP isn't configured"
