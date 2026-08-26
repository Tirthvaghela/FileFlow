from datetime import datetime, timedelta, timezone

from services.stats_service import get_stats, get_weekly_reports


class TestGetStats:
    def test_empty_db_returns_all_zeros(self, db_session):
        stats = get_stats(db_session, 1)

        assert stats.total_files_organized == 0
        assert stats.duplicates_detected == 0
        assert stats.files_archived == 0
        assert stats.storage_saved_bytes == 0
        assert stats.today_count == 0
        assert stats.by_category == []
        assert len(stats.last_7_days) == 7

    def test_total_files_organized_counts_every_organized_action(self, db_session, log_factory):
        # total_files_organized must count all three "the file landed
        # somewhere" actions, not just a plain "moved" -- renamed_and_moved
        # (duplicate collision) and replaced both organize a file too.
        log_factory(action="moved")
        log_factory(action="renamed_and_moved")
        log_factory(action="replaced")
        log_factory(action="duplicate_skipped")
        log_factory(action="archived")

        stats = get_stats(db_session, 1)

        assert stats.total_files_organized == 3
        assert stats.duplicates_detected == 1
        assert stats.files_archived == 1

    def test_storage_saved_only_sums_duplicate_skipped_sizes(self, db_session, log_factory):
        log_factory(action="moved", file_size=1000)
        log_factory(action="duplicate_skipped", file_size=250)
        log_factory(action="duplicate_skipped", file_size=50)

        stats = get_stats(db_session, 1)

        assert stats.storage_saved_bytes == 300

    def test_today_count_excludes_entries_from_earlier_days(self, db_session, log_factory):
        now = datetime.now(timezone.utc)
        log_factory(action="moved", timestamp=now)
        log_factory(action="moved", timestamp=now - timedelta(days=1, hours=1))

        stats = get_stats(db_session, 1)

        assert stats.today_count == 1
        assert stats.total_files_organized == 2

    def test_by_category_groups_and_counts_correctly(self, db_session, log_factory):
        log_factory(category="Documents")
        log_factory(category="Documents")
        log_factory(category="Images")
        log_factory(category="Images", action="duplicate_skipped")  # not organized

        stats = get_stats(db_session, 1)
        by_name = {row.category: row.count for row in stats.by_category}

        assert by_name["Documents"] == 2
        assert by_name["Images"] == 1

    def test_last_7_days_places_entries_in_the_correct_bucket(self, db_session, log_factory):
        now = datetime.now(timezone.utc)
        log_factory(action="moved", timestamp=now)
        log_factory(action="moved", timestamp=now - timedelta(days=3))
        log_factory(action="moved", timestamp=now - timedelta(days=10))  # outside the window

        stats = get_stats(db_session, 1)

        assert len(stats.last_7_days) == 7
        assert stats.last_7_days[-1].count == 1  # today, last bucket
        assert stats.last_7_days[-4].count == 1  # 3 days ago
        assert sum(d.count for d in stats.last_7_days) == 2


class TestGetWeeklyReports:
    def test_default_returns_four_weeks_most_recent_first(self, db_session):
        reports = get_weekly_reports(db_session, 1)
        assert len(reports) == 4
        # each window is 7 days, and windows must be contiguous/non-overlapping
        assert reports[0].week_start > reports[1].week_start

    def test_a_log_from_ten_days_ago_lands_in_week_two_not_week_one(self, db_session, log_factory):
        now = datetime.now(timezone.utc)
        log_factory(action="moved", timestamp=now)  # this week
        log_factory(action="moved", timestamp=now - timedelta(days=10))  # last week

        reports = get_weekly_reports(db_session, 1, weeks=2)

        assert reports[0].files_organized == 1
        assert reports[1].files_organized == 1

    def test_duplicates_and_archives_are_scoped_to_their_own_week(self, db_session, log_factory):
        now = datetime.now(timezone.utc)
        log_factory(action="duplicate_skipped", timestamp=now, file_size=500)
        log_factory(action="archived", timestamp=now - timedelta(days=10))

        reports = get_weekly_reports(db_session, 1, weeks=2)

        assert reports[0].duplicates_removed == 1
        assert reports[0].storage_optimized_bytes == 500
        assert reports[0].files_archived == 0
        assert reports[1].files_archived == 1

    def test_weeks_param_controls_result_length(self, db_session):
        assert len(get_weekly_reports(db_session, 1, weeks=1)) == 1
        assert len(get_weekly_reports(db_session, 1, weeks=6)) == 6
