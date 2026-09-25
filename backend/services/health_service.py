"""Organization Health Dashboard: a single read-only aggregation over
FileFlow's EXISTING capabilities (Explainable Organization/Organization
Preview, AI Unclassified Suggestions, Rule Conflict Detector, Smart
Duplicate Groups, and activity history) -- answering "how healthy and
organized is my workspace right now?".

THIS MODULE IS AN AGGREGATION LAYER ONLY. It never re-implements
classification, duplicate hashing, rule conflict detection, or activity
semantics -- it only calls the real services that already do
(automation.organizer.plan_organize_existing,
automation.file_ops.build_duplicate_groups_result,
services.rule_conflict_service.analyze_conflicts) and counts/labels their
already-computed output. It never moves/renames/deletes a file, never
creates or modifies a rule, and never writes an activity_log row.

get_organization_health() is the only entry point routes.py calls. Each of
the four sections below is computed independently and defensively -- one
subsystem raising never takes down the rest of the response (Phase 21 of
the spec this implements): it's reported as `status: "unavailable"`
instead of turning the whole endpoint into a 500."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from automation.file_ops import build_duplicate_groups_result
from automation.organizer import plan_organize_existing
from config.settings import all_watch_folders
from models.schemas import (
    ActivityHealthStats,
    ActivityWindowStats,
    DuplicateHealthStats,
    FileHealthStats,
    OrganizationHealthResponse,
    RuleHealthStats,
)
from rules.rule_engine import get_rule_engine
from services.agent_service import is_agent_connected
from services.rule_conflict_service import analyze_conflicts
from services.stats_service import ORGANIZED_ACTIONS

logger = logging.getLogger("fileflow.health")

# The backend has no way to inspect a connected agent's remote filesystem
# directly (Phase 14) -- rather than automatically queuing an expensive
# agent scan every time this dashboard loads, these two filesystem-
# dependent sections are reported unavailable for an agent-connected
# account, with a pointer to the existing feature that already knows how to
# fetch that data on demand (its own enqueue/poll dance), so no new agent
# command type or permanent agent infrastructure is introduced here.
AGENT_UNAVAILABLE_FILES = (
    "File classification health isn't available yet for a connected agent -- "
    "use Unclassified Suggestions to check now."
)
AGENT_UNAVAILABLE_DUPLICATES = (
    "Duplicate scanning isn't available yet for a connected agent -- "
    "use Duplicate Files to check now."
)


def _files_health(db, user: dict) -> FileHealthStats:
    if is_agent_connected(user):
        return FileHealthStats(status="unavailable", message=AGENT_UNAVAILABLE_FILES)

    items = plan_organize_existing(db, user)
    scanned = len(items)
    errors = sum(1 for i in items if i["status"] == "error")
    unclassified = sum(1 for i in items if i["status"] == "no_match")
    classified = scanned - errors - unclassified
    eligible = classified + unclassified
    coverage = round(classified / eligible * 100, 1) if eligible else None

    return FileHealthStats(
        scanned=scanned,
        classified=classified,
        unclassified=unclassified,
        errors=errors,
        classification_coverage_percent=coverage,
    )


def _duplicates_health(user: dict) -> DuplicateHealthStats:
    if is_agent_connected(user):
        return DuplicateHealthStats(status="unavailable", message=AGENT_UNAVAILABLE_DUPLICATES)

    # max_groups=0: this card only ever needs the full-scan summary counts,
    # never per-group detail -- see build_duplicate_groups_result()'s own
    # docstring for why those counts are unaffected by the cap.
    raw = build_duplicate_groups_result(all_watch_folders(user), max_groups=0)
    return DuplicateHealthStats(
        groups=raw["duplicate_groups"],
        duplicate_files=raw["duplicate_files"],
        potential_redundant_bytes=raw["potential_redundant_bytes"],
    )


def _rules_health(db, user: dict) -> RuleHealthStats:
    watch_root = Path(user["watch_folder"])
    engine = get_rule_engine(db, user["id"], watch_root)
    rules = engine.rules

    large_file_rule_present = bool(rules.get("large_file_threshold_mb"))
    active = (
        len(rules.get("keyword_rules") or [])
        + len(rules.get("content_keyword_rules") or [])
        + len(rules.get("regex_rules") or [])
        + len(rules.get("date_rules") or [])
        + len(rules.get("extension_rules") or {})
        + (1 if large_file_rule_present and rules.get("large_file_enabled", True) else 0)
    )
    disabled = (
        len(rules.get("disabled_keyword_rules") or [])
        + len(rules.get("disabled_content_keyword_rules") or [])
        + len(rules.get("disabled_regex_rules") or [])
        + len(rules.get("disabled_date_rules") or [])
        + len(rules.get("disabled_extension_rules") or {})
        + (1 if large_file_rule_present and not rules.get("large_file_enabled", True) else 0)
    )

    result = analyze_conflicts(rules, watch_root)
    redundant = sum(1 for c in result.conflicts if c.type == "redundant_rule")

    return RuleHealthStats(
        active=active,
        disabled=disabled,
        conflicts_total=result.total,
        conflicts_high=result.high,
        conflicts_warning=result.warnings,
        redundant_rules=redundant,
    )


def _window_counts(db, user_id: int, since: datetime) -> ActivityWindowStats:
    coll = db.activity_log
    organized = coll.count_documents(
        {"user_id": user_id, "action": {"$in": ORGANIZED_ACTIONS}, "timestamp": {"$gte": since}}
    )
    skipped = coll.count_documents(
        {"user_id": user_id, "action": "duplicate_skipped", "timestamp": {"$gte": since}}
    )
    return ActivityWindowStats(organized=organized, skipped=skipped)


def _activity_health(db, user_id: int) -> ActivityHealthStats:
    now = datetime.now(timezone.utc)
    return ActivityHealthStats(
        last_24_hours=_window_counts(db, user_id, now - timedelta(hours=24)),
        last_7_days=_window_counts(db, user_id, now - timedelta(days=7)),
        last_30_days=_window_counts(db, user_id, now - timedelta(days=30)),
    )


def get_organization_health(db, user: dict) -> OrganizationHealthResponse:
    """Read-only: the single entry point routes.py calls. Never saves
    anything, never organizes, and never touches a rule or the filesystem
    beyond what plan_organize_existing()/build_duplicate_groups_result()
    already read for their own existing features."""
    try:
        files = _files_health(db, user)
    except Exception:
        logger.exception("Health: file classification aggregation failed")
        files = FileHealthStats(
            status="unavailable", message="File classification data is temporarily unavailable."
        )

    try:
        duplicates = _duplicates_health(user)
    except Exception:
        logger.exception("Health: duplicate aggregation failed")
        duplicates = DuplicateHealthStats(
            status="unavailable", message="Duplicate analysis is temporarily unavailable."
        )

    try:
        rules = _rules_health(db, user)
    except Exception:
        logger.exception("Health: rule conflict aggregation failed")
        rules = RuleHealthStats(
            status="unavailable", message="Rule health data is temporarily unavailable."
        )

    try:
        activity = _activity_health(db, user["id"])
    except Exception:
        logger.exception("Health: activity aggregation failed")
        activity = ActivityHealthStats(
            status="unavailable", message="Activity history is temporarily unavailable."
        )

    return OrganizationHealthResponse(
        generated_at=datetime.now(timezone.utc),
        agent_connected=is_agent_connected(user),
        files=files,
        duplicates=duplicates,
        rules=rules,
        activity=activity,
    )
