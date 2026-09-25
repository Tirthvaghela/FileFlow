"""Rule Conflict Detector: explains where two or more of an account's rules
can match the same file, and what the REAL classifier (rules/classifier.py)
actually does about it.

THE CLASSIFIER IS THE SOURCE OF TRUTH. THIS MODULE NEVER INVENTS A SECOND,
INDEPENDENT PRECEDENCE SYSTEM.

Two separate techniques are used, deliberately kept apart:

1. Same-list structural analysis (_keyword_like_conflicts, _regex_conflicts,
   _date_conflicts): keyword_rules, content_keyword_rules, regex_rules and
   date_rules are each evaluated in stored list order, first match wins
   (see classify_file_explained). Whether an earlier rule's condition
   *provably* covers every file a later one could ever match is a fact
   about the two rules' own configured values alone (a substring
   relationship, a threshold comparison) -- no synthetic file is needed,
   and the result is a PROVEN "shadowed_rule"/"redundant_rule" finding.

2. Cross-type candidate evaluation (_cross_type_conflicts): for rule types
   that impose a condition on a filename or size (keyword, extension,
   large_file, regex), a short synthetic candidate built ONLY from those
   rules' own configured values (never a real file, never fabricated
   content or mtime) is run through the real classify_file_explained() --
   the exact function a real file is classified by -- to see which rule
   actually wins and what it sends the file to.

content_keyword and date rules are EXCLUDED from cross-type candidate
evaluation on purpose: classify_file_explained() requires a real file_path
for both (to read content / stat mtime), which this analysis never has and
never fakes. Rather than silently skip them or force a guess, a single
bounded "unverifiable_overlap" notice discloses that gap instead.

analyze_conflicts() never writes to the database, never touches the
filesystem, and never calls classify on a real file -- purely advisory,
read-only analysis of the rules dict itself."""

import re
from pathlib import Path

from models.schemas import (
    RuleConflict,
    RuleConflictAnalysisResult,
    RuleConflictExample,
    RuleConflictRuleRef,
)
from rules.classifier import classify_file_explained, is_within_watch_folder

TYPE_LABEL = {
    "keyword": "Keyword",
    "content_keyword": "Content keyword",
    "regex": "Regex",
    "extension": "Extension",
    "large_file": "File size",
    "date": "File age",
}

# Rule types a synthetic candidate CAN be built to satisfy, without ever
# reading a real file's content or modification time.
_GENERATABLE_TYPES = ("keyword", "extension", "large_file")

# Defensive ceilings only (Phase 20 performance) -- a real personal rule set
# is realistically a few dozen entries; nobody should ever actually hit
# these in normal use.
MAX_RULES_PER_LIST = 100
MAX_CONFLICTS_RETURNED = 50

_DEFAULT_CANDIDATE_SIZE_BYTES = 2048


def _describe(rule_type: str, rule: dict) -> str:
    """Mirrors rules.classifier._explanation()'s own rule_name formatting
    exactly, so a conflict never describes a rule any differently than
    Feature 1's explanation would once it actually matches."""
    if rule_type == "keyword":
        return f'Keyword "{rule["keyword"]}"'
    if rule_type == "content_keyword":
        return f'File content contains "{rule["keyword"]}"'
    if rule_type == "regex":
        return f'Regex pattern "{rule["pattern"]}"'
    if rule_type == "extension":
        return f'Extension "{rule["extension"]}"'
    if rule_type == "large_file":
        return f'Large file (over {rule["threshold_mb"]} MB)'
    return f'File age (over {rule["older_than_days"]} days old)'


def _ref(rule_type: str, rule: dict) -> RuleConflictRuleRef:
    return RuleConflictRuleRef(
        rule_type=rule_type, description=_describe(rule_type, rule), destination=rule["folder"]
    )


def _valid_rules(rules: dict, watch_root: Path) -> dict[str, list[dict]]:
    """Every user-editable rule (the six SUPPORTED_RULE_TYPES
    services.ai_rule_service also uses), normalized to a uniform
    {value..., folder} shape and filtered to only those whose destination
    actually resolves inside the watch folder. classify_file_explained()
    treats an invalid-destination rule as invisible (it's skipped, never
    attributed as a match) -- this filter keeps that same behavior true
    here, so this detector never warns about a "conflict" that could never
    actually happen. disabled_* rule lists are never read: they're inert,
    classify_file_explained() never evaluates them either."""
    out: dict[str, list[dict]] = {
        "keyword": [],
        "content_keyword": [],
        "regex": [],
        "extension": [],
        "large_file": [],
        "date": [],
    }

    for r in (rules.get("keyword_rules") or [])[:MAX_RULES_PER_LIST]:
        if is_within_watch_folder(r["folder"], watch_root):
            out["keyword"].append({"keyword": r["keyword"], "folder": r["folder"]})

    for r in (rules.get("content_keyword_rules") or [])[:MAX_RULES_PER_LIST]:
        if is_within_watch_folder(r["folder"], watch_root):
            out["content_keyword"].append({"keyword": r["keyword"], "folder": r["folder"]})

    for r in (rules.get("regex_rules") or [])[:MAX_RULES_PER_LIST]:
        if is_within_watch_folder(r["folder"], watch_root):
            out["regex"].append({"pattern": r["pattern"], "folder": r["folder"]})

    for ext, folder in list((rules.get("extension_rules") or {}).items())[:MAX_RULES_PER_LIST]:
        if is_within_watch_folder(folder, watch_root):
            out["extension"].append({"extension": ext, "folder": folder})

    for r in (rules.get("date_rules") or [])[:MAX_RULES_PER_LIST]:
        if is_within_watch_folder(r["folder"], watch_root):
            out["date"].append({"older_than_days": r["older_than_days"], "folder": r["folder"]})

    threshold_mb = rules.get("large_file_threshold_mb")
    if rules.get("large_file_enabled", True) and threshold_mb:
        folder = rules.get("large_file_folder", "Large Files")
        if is_within_watch_folder(folder, watch_root):
            out["large_file"].append({"threshold_mb": threshold_mb, "folder": folder})

    return out


def _keyword_like_conflicts(rule_type: str, rules_list: list[dict]) -> list[RuleConflict]:
    """keyword_rules and content_keyword_rules share the exact same
    evaluation semantics: stored list order, first substring match wins.
    If an earlier rule's keyword is itself a substring of a later rule's
    keyword, then EVERY filename (or content snippet) containing the later
    keyword necessarily also contains the earlier one -- so the earlier
    rule, evaluated first, always wins for that entire overlap. That's
    provable from the two keywords alone, no synthetic file needed."""
    conflicts: list[RuleConflict] = []
    n = len(rules_list)
    for i in range(n):
        for j in range(i + 1, n):
            earlier, later = rules_list[i], rules_list[j]
            kw_earlier = earlier["keyword"].lower()
            kw_later = later["keyword"].lower()
            if kw_earlier not in kw_later:
                continue
            same_destination = earlier["folder"] == later["folder"]
            identical = kw_earlier == kw_later
            earlier_desc = _describe(rule_type, earlier)
            later_desc = _describe(rule_type, later)
            example_name = f"{later['keyword']}.dat"
            if same_destination:
                message = (
                    f'"{earlier_desc}" and "{later_desc}" are identical and both point to '
                    f'"{earlier["folder"]}" -- one of them has no effect.'
                    if identical
                    else (
                        f'"{later_desc}" has no effect: it is evaluated after "{earlier_desc}", and '
                        f'every file it would match already matches "{earlier_desc}" first -- both '
                        f'send it to the same place ("{earlier["folder"]}").'
                    )
                )
                conflicts.append(
                    RuleConflict(
                        severity="info",
                        type="redundant_rule",
                        rules=[_ref(rule_type, earlier), _ref(rule_type, later)],
                        example=RuleConflictExample(
                            filename=example_name, destination=earlier["folder"], winning_rule=earlier_desc
                        ),
                        message=message,
                    )
                )
            else:
                conflicts.append(
                    RuleConflict(
                        severity="high",
                        type="shadowed_rule",
                        rules=[_ref(rule_type, earlier), _ref(rule_type, later)],
                        example=RuleConflictExample(
                            filename=example_name, destination=earlier["folder"], winning_rule=earlier_desc
                        ),
                        message=(
                            f'"{later_desc}" can never take effect: every file it would match also '
                            f'matches "{earlier_desc}", which is evaluated first and sends it to '
                            f'"{earlier["folder"]}" instead of "{later["folder"]}".'
                        ),
                    )
                )
    return conflicts


def _regex_conflicts(rules_list: list[dict]) -> list[RuleConflict]:
    """Only EXACT duplicate patterns are reported -- proving one regex's
    match set is a subset of another's in general is undecidable, and this
    detector never guesses at something it can't prove (Phase 9)."""
    conflicts: list[RuleConflict] = []
    n = len(rules_list)
    for i in range(n):
        for j in range(i + 1, n):
            earlier, later = rules_list[i], rules_list[j]
            if earlier["pattern"] != later["pattern"]:
                continue
            same_destination = earlier["folder"] == later["folder"]
            earlier_desc = _describe("regex", earlier)
            later_desc = _describe("regex", later)
            if same_destination:
                conflicts.append(
                    RuleConflict(
                        severity="info",
                        type="redundant_rule",
                        rules=[_ref("regex", earlier), _ref("regex", later)],
                        example=None,
                        message=(
                            f'"{earlier_desc}" and "{later_desc}" are identical and both point to '
                            f'"{earlier["folder"]}" -- one of them has no effect.'
                        ),
                    )
                )
            else:
                conflicts.append(
                    RuleConflict(
                        severity="high",
                        type="shadowed_rule",
                        rules=[_ref("regex", earlier), _ref("regex", later)],
                        example=None,
                        message=(
                            f'"{later_desc}" can never take effect: it is identical to "{earlier_desc}", '
                            f'which is evaluated first and sends matching files to "{earlier["folder"]}" '
                            f'instead of "{later["folder"]}".'
                        ),
                    )
                )
    return conflicts


def _date_conflicts(rules_list: list[dict]) -> list[RuleConflict]:
    """Same first-match-wins list semantics as above. A file satisfying
    "older than N days" also satisfies "older than M days" for any M <= N
    -- so if an earlier rule's threshold is <= a later rule's, the earlier
    rule always wins the overlap, proven from the two thresholds alone."""
    conflicts: list[RuleConflict] = []
    n = len(rules_list)
    for i in range(n):
        for j in range(i + 1, n):
            earlier, later = rules_list[i], rules_list[j]
            if earlier["older_than_days"] > later["older_than_days"]:
                continue
            same_destination = earlier["folder"] == later["folder"]
            identical = earlier["older_than_days"] == later["older_than_days"]
            earlier_desc = _describe("date", earlier)
            later_desc = _describe("date", later)
            example = RuleConflictExample(
                filename=None, destination=earlier["folder"], winning_rule=earlier_desc
            )
            if same_destination:
                message = (
                    f'"{earlier_desc}" and "{later_desc}" are identical and both point to '
                    f'"{earlier["folder"]}" -- one of them has no effect.'
                    if identical
                    else (
                        f'"{later_desc}" has no effect: any file old enough to match it is also old '
                        f'enough to match "{earlier_desc}" first, and both send it to the same place '
                        f'("{earlier["folder"]}").'
                    )
                )
                conflicts.append(
                    RuleConflict(
                        severity="info",
                        type="redundant_rule",
                        rules=[_ref("date", earlier), _ref("date", later)],
                        example=example,
                        message=message,
                    )
                )
            else:
                conflicts.append(
                    RuleConflict(
                        severity="high",
                        type="shadowed_rule",
                        rules=[_ref("date", earlier), _ref("date", later)],
                        example=example,
                        message=(
                            f'"{later_desc}" can never take effect: any file old enough to match it is '
                            f'also old enough to match "{earlier_desc}", which is evaluated first and '
                            f'sends it to "{earlier["folder"]}" instead of "{later["folder"]}".'
                        ),
                    )
                )
    return conflicts


def _build_candidate(type_a: str, rule_a: dict, type_b: str, rule_b: dict) -> tuple[str, int] | None:
    """A synthetic (filename, size_bytes) candidate satisfying both rules'
    OWN configured preconditions -- built only from generatable types
    (keyword, extension, large_file), never a real file."""
    parts = {type_a: rule_a, type_b: rule_b}
    if not set(parts) <= set(_GENERATABLE_TYPES):
        return None
    keyword = parts.get("keyword", {}).get("keyword")
    extension = parts.get("extension", {}).get("extension") or ".dat"
    name = f"{keyword}{extension}" if keyword else f"sample{extension}"
    size = _DEFAULT_CANDIDATE_SIZE_BYTES
    if "large_file" in parts:
        size = parts["large_file"]["threshold_mb"] * 1024 * 1024 + 1
    return name, size


def _regex_candidate_from_other(other_type: str, other_rule: dict) -> tuple[str, int] | None:
    if other_type == "keyword":
        return f"{other_rule['keyword']}.dat", _DEFAULT_CANDIDATE_SIZE_BYTES
    if other_type == "extension":
        return f"sample{other_rule['extension']}", _DEFAULT_CANDIDATE_SIZE_BYTES
    if other_type == "large_file":
        return "sample.dat", other_rule["threshold_mb"] * 1024 * 1024 + 1
    return None


def _matches_explanation(rule_type: str, rule: dict, explanation: dict) -> bool:
    if rule_type == "keyword":
        return explanation["matched_value"] == rule["keyword"]
    if rule_type == "extension":
        return explanation["matched_value"] == rule["extension"]
    if rule_type == "regex":
        return explanation["matched_value"] == rule["pattern"]
    if rule_type == "large_file":
        return True
    return False


def _evaluate_pair(
    rules: dict,
    watch_root: Path,
    name: str,
    size: int,
    type_a: str,
    rule_a: dict,
    type_b: str,
    rule_b: dict,
) -> RuleConflict | None:
    """Runs the synthetic candidate through the REAL classify_file_explained
    -- the exact function a real file would be classified by, against the
    account's WHOLE actual rule set, not a hand-rolled priority table.
    Returns None if the result can't be confidently attributed to rule_a or
    rule_b specifically (e.g. some unrelated third rule happened to win) --
    this detector never claims a relationship it can't demonstrate."""
    explanation = classify_file_explained(rules, name, size, watch_root, file_path=None)
    winner_type = explanation["match_type"]

    if winner_type == type_a and _matches_explanation(type_a, rule_a, explanation):
        winner_type_r, winner_rule, loser_type, loser_rule = type_a, rule_a, type_b, rule_b
    elif winner_type == type_b and _matches_explanation(type_b, rule_b, explanation):
        winner_type_r, winner_rule, loser_type, loser_rule = type_b, rule_b, type_a, rule_a
    else:
        return None

    winner_destination = explanation["destination"]
    loser_destination = loser_rule["folder"]
    winner_desc = _describe(winner_type_r, winner_rule)

    if winner_destination == loser_destination:
        return RuleConflict(
            severity="info",
            type="overlap",
            rules=[_ref(type_a, rule_a), _ref(type_b, rule_b)],
            example=RuleConflictExample(
                filename=name, destination=winner_destination, winning_rule=winner_desc
            ),
            message=(
                f'Both rules can match {name} and agree on the same destination '
                f'("{winner_destination}"), so the result is the same either way.'
            ),
        )

    reason = f"{TYPE_LABEL[winner_type_r]} rules are evaluated before {TYPE_LABEL[loser_type].lower()} rules."
    return RuleConflict(
        severity="warning",
        type="precedence_overlap",
        rules=[_ref(type_a, rule_a), _ref(type_b, rule_b)],
        example=RuleConflictExample(
            filename=name, destination=winner_destination, winning_rule=winner_desc
        ),
        message=f"Both rules can match {name}. {reason}",
    )


def _cross_type_conflicts(
    normalized: dict[str, list[dict]], rules: dict, watch_root: Path
) -> list[RuleConflict]:
    conflicts: list[RuleConflict] = []

    generatable = [(t, r) for t in _GENERATABLE_TYPES for r in normalized[t]]
    for i in range(len(generatable)):
        for j in range(i + 1, len(generatable)):
            type_a, rule_a = generatable[i]
            type_b, rule_b = generatable[j]
            if type_a == type_b:
                continue
            candidate = _build_candidate(type_a, rule_a, type_b, rule_b)
            if candidate is None:
                continue
            name, size = candidate
            c = _evaluate_pair(rules, watch_root, name, size, type_a, rule_a, type_b, rule_b)
            if c:
                conflicts.append(c)

    for other_type in _GENERATABLE_TYPES:
        for other_rule in normalized[other_type]:
            built = _regex_candidate_from_other(other_type, other_rule)
            if built is None:
                continue
            name, size = built
            for regex_rule in normalized["regex"]:
                try:
                    if not re.search(regex_rule["pattern"], name, re.IGNORECASE):
                        continue
                except re.error:
                    continue
                c = _evaluate_pair(rules, watch_root, name, size, "regex", regex_rule, other_type, other_rule)
                if c:
                    conflicts.append(c)

    return conflicts


def _unverifiable_notice(
    rule_type: str, rules_list: list[dict], other_rules_present: bool
) -> RuleConflict | None:
    """A single, bounded disclosure -- never a per-pair guess -- that
    content-keyword/file-age rules could overlap with other rules but this
    analysis can't check that without reading a real file's content or
    modification time, which it deliberately never does (Phase 6)."""
    if not rules_list or not other_rules_present:
        return None
    plural = "s" if len(rules_list) != 1 else ""
    if rule_type == "content_keyword":
        noun, needs = "content-keyword rule", "a file's actual content"
    else:
        noun, needs = "file-age rule", "a file's actual modification date"
    return RuleConflict(
        severity="info",
        type="unverifiable_overlap",
        rules=[_ref(rule_type, r) for r in rules_list],
        example=None,
        message=(
            f"{len(rules_list)} {noun}{plural} could overlap with your other rules, but this can't be "
            f"checked without reading {needs} -- this analysis only compares rules against each other, "
            f"it never reads your files."
        ),
    )


def analyze_conflicts(rules: dict, watch_root: Path) -> RuleConflictAnalysisResult:
    """Read-only: the single entry point routes.py calls. Never saves
    anything, never organizes, never touches the filesystem."""
    normalized = _valid_rules(rules, watch_root)

    conflicts: list[RuleConflict] = []
    conflicts += _keyword_like_conflicts("keyword", normalized["keyword"])
    conflicts += _keyword_like_conflicts("content_keyword", normalized["content_keyword"])
    conflicts += _regex_conflicts(normalized["regex"])
    conflicts += _date_conflicts(normalized["date"])
    conflicts += _cross_type_conflicts(normalized, rules, watch_root)

    other_than_content = sum(len(v) for k, v in normalized.items() if k != "content_keyword")
    other_than_date = sum(len(v) for k, v in normalized.items() if k != "date")
    notice = _unverifiable_notice("content_keyword", normalized["content_keyword"], other_than_content > 0)
    if notice:
        conflicts.append(notice)
    notice = _unverifiable_notice("date", normalized["date"], other_than_date > 0)
    if notice:
        conflicts.append(notice)

    rules_checked = sum(len(v) for v in normalized.values())
    truncated = len(conflicts) > MAX_CONFLICTS_RETURNED
    conflicts = conflicts[:MAX_CONFLICTS_RETURNED]

    return RuleConflictAnalysisResult(
        conflicts=conflicts,
        total=len(conflicts),
        info=sum(1 for c in conflicts if c.severity == "info"),
        warnings=sum(1 for c in conflicts if c.severity == "warning"),
        high=sum(1 for c in conflicts if c.severity == "high"),
        rules_checked=rules_checked,
        truncated=truncated,
    )
