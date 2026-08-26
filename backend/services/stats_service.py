from datetime import datetime, timedelta, timezone

from models.schemas import (
    CategoryStat,
    DailyStat,
    StatsOut,
    WeeklyReportStat,
)

ORGANIZED_ACTIONS = ["moved", "renamed_and_moved", "replaced"]


def _sum_file_size(db, match: dict) -> int:
    agg = list(
        db.activity_log.aggregate(
            [{"$match": match}, {"$group": {"_id": None, "total": {"$sum": "$file_size"}}}]
        )
    )
    return agg[0]["total"] if agg else 0


def get_stats(db, user_id: int) -> StatsOut:
    coll = db.activity_log

    total_files_organized = coll.count_documents(
        {"user_id": user_id, "action": {"$in": ORGANIZED_ACTIONS}}
    )
    duplicates_detected = coll.count_documents(
        {"user_id": user_id, "action": "duplicate_skipped"}
    )
    files_archived = coll.count_documents({"user_id": user_id, "action": "archived"})
    storage_saved_bytes = _sum_file_size(
        db, {"user_id": user_id, "action": "duplicate_skipped"}
    )

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_count = coll.count_documents(
        {
            "user_id": user_id,
            "action": {"$in": ORGANIZED_ACTIONS},
            "timestamp": {"$gte": today_start},
        }
    )

    category_rows = list(
        coll.aggregate(
            [
                {"$match": {"user_id": user_id, "action": {"$in": ORGANIZED_ACTIONS}}},
                {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            ]
        )
    )
    by_category = [CategoryStat(category=r["_id"], count=r["count"]) for r in category_rows]

    last_7_days: list[DailyStat] = []
    for i in range(6, -1, -1):
        day_start = today_start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        count = coll.count_documents(
            {
                "user_id": user_id,
                "action": {"$in": ORGANIZED_ACTIONS},
                "timestamp": {"$gte": day_start, "$lt": day_end},
            }
        )
        last_7_days.append(DailyStat(date=day_start.strftime("%Y-%m-%d"), count=count))

    return StatsOut(
        total_files_organized=total_files_organized,
        duplicates_detected=duplicates_detected,
        files_archived=files_archived,
        storage_saved_bytes=storage_saved_bytes,
        today_count=today_count,
        by_category=by_category,
        last_7_days=last_7_days,
    )


def get_weekly_reports(db, user_id: int, weeks: int = 4) -> list[WeeklyReportStat]:
    """Rolling 7-day windows ending today, most recent first."""
    coll = db.activity_log
    window_end = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)

    reports: list[WeeklyReportStat] = []
    for _ in range(weeks):
        window_start = window_end - timedelta(days=7)
        window_filter = {"user_id": user_id, "timestamp": {"$gte": window_start, "$lt": window_end}}

        files_organized = coll.count_documents(
            {"action": {"$in": ORGANIZED_ACTIONS}, **window_filter}
        )
        duplicates_removed = coll.count_documents(
            {"action": "duplicate_skipped", **window_filter}
        )
        storage_optimized_bytes = _sum_file_size(
            db, {"action": "duplicate_skipped", **window_filter}
        )
        files_archived = coll.count_documents({"action": "archived", **window_filter})

        reports.append(
            WeeklyReportStat(
                week_start=window_start.strftime("%Y-%m-%d"),
                week_end=(window_end - timedelta(days=1)).strftime("%Y-%m-%d"),
                files_organized=files_organized,
                duplicates_removed=duplicates_removed,
                storage_optimized_bytes=storage_optimized_bytes,
                files_archived=files_archived,
            )
        )
        window_end = window_start

    return reports
