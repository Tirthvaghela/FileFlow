import re
from pathlib import Path

from models.schemas import CategoryStat, RulePreviewOut

MAX_SAMPLES = 20


def preview_rule(db, user_id: int, rule_type: str, match: str) -> RulePreviewOut:
    """Show which already-organized files a not-yet-saved rule would have
    matched, purely as a read-only query against activity_log -- no rule is
    applied and no file is touched. Matching mirrors RuleEngine.classify()
    exactly (suffix equality for extensions, case-insensitive substring for
    keywords), done in Python rather than a Mongo regex so an
    extension/keyword containing regex metacharacters can't be misread."""
    match = match.strip()
    if not match:
        return RulePreviewOut(matched_count=0, by_category=[], samples=[])

    rows = list(db.activity_log.find({"user_id": user_id}))

    if rule_type == "extension":
        ext = (match if match.startswith(".") else f".{match}").lower()
        matches = [r for r in rows if Path(r["original_filename"]).suffix.lower() == ext]
    elif rule_type == "regex":
        try:
            pattern = re.compile(match, re.IGNORECASE)
        except re.error:
            # Same "not ready yet" treatment as an empty match above --
            # this fires on every keystroke of a pattern the user is still
            # typing, so a half-finished pattern must not read as an error.
            return RulePreviewOut(matched_count=0, by_category=[], samples=[])
        matches = [r for r in rows if pattern.search(r["original_filename"])]
    else:
        needle = match.lower()
        matches = [r for r in rows if needle in r["original_filename"].lower()]

    by_category: dict[str, int] = {}
    for row in matches:
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1

    return RulePreviewOut(
        matched_count=len(matches),
        by_category=[CategoryStat(category=c, count=n) for c, n in by_category.items()],
        samples=[r["final_filename"] for r in matches[:MAX_SAMPLES]],
    )
