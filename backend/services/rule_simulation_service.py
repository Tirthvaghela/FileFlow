from pathlib import Path

from models.schemas import RuleSimulationChange, RuleSimulationResult
from rules.classifier import classify_file

# Recent-history only, not the whole activity_log -- this runs synchronously
# on a request (unlike the scheduled sweeps), and a bounded, most-recent
# sample is exactly what "would this new rule have changed anything
# lately" needs.
HISTORY_LIMIT = 300
MAX_CHANGES_RETURNED = 50


def simulate_rules(db, user: dict, candidate_rules: dict) -> RuleSimulationResult:
    """Read-only: re-classifies each of the account's recent organized files
    using a not-yet-saved candidate rule set (classify_file() is pure -- no
    database write, no filesystem write, file_path omitted so date/content
    rules simply never match, exactly as list_category_files-style preview
    code already relies on elsewhere) and reports which ones would now land
    somewhere different. Never calls RuleEngine.save() or touches a file."""
    watch_root = Path(user["watch_folder"])
    rows = (
        db.activity_log.find({"user_id": user["id"], "action": {"$ne": "deleted"}})
        .sort("_id", -1)
        .limit(HISTORY_LIMIT)
    )

    compared = 0
    total_changed = 0
    changes: list[RuleSimulationChange] = []
    for row in rows:
        compared += 1
        predicted = classify_file(
            candidate_rules,
            row["original_filename"],
            row.get("file_size", 0),
            watch_root,
            file_path=None,
        )
        if predicted == row["category"]:
            continue
        total_changed += 1
        if len(changes) < MAX_CHANGES_RETURNED:
            changes.append(
                RuleSimulationChange(
                    filename=row["final_filename"],
                    file_size_bytes=row.get("file_size", 0),
                    previous_category=row["category"],
                    new_category=predicted,
                )
            )

    return RuleSimulationResult(
        compared_count=compared,
        unchanged_count=compared - total_changed,
        changes=changes,
    )
