"""AI Unclassified File Suggestions: for files the real classifier reports
as no-match, ask the AI what they might be and where they could belong --
strictly advisory, never a second classifier and never a save/organize path
of its own.

AI MAY SUGGEST. AI MUST NOT DECIDE OR EXECUTE.

generate_unclassified_suggestions() below is the only entry point routes.py
calls. It never moves/renames/deletes a file and never writes to
activity_log or rules -- a `suggested_rule` only ever becomes a real rule
through the pre-existing PUT /api/rules, exactly like an AI Rule Generator
proposal, once the user explicitly reviews and saves it (see
frontend/src/utils/ruleForm.js, shared by both features).

"Unclassified" here means exactly one thing: plan_organize_existing()'s (or
the agent's equivalent) own `status == "no_match"`, itself built only from
classify_file_explained()'s real `match_type == "default"` -- see
automation/organizer.py. There is no second, independent definition of
"no matching rule" anywhere in this module.
"""

import json
import logging
import re
from pathlib import Path

from pydantic import ValidationError

from automation.organizer import plan_organize_existing
from config.settings import settings
from models.schemas import (
    AIRuleProposal,
    UnclassifiedSuggestion,
    UnclassifiedSuggestionResult,
)
from services.agent_service import enqueue_agent_command, is_agent_connected
from services.ai_provider import (
    AIProviderError,
    generate_suggestion_completion,
)
from services.ai_rule_service import _validate_candidate

logger = logging.getLogger("fileflow.ai")

UNAVAILABLE_MESSAGE = "AI service is temporarily unavailable. Please try again shortly."

# A shared prefix/suffix separator immediately before a trailing run of
# digits, e.g. "invoice_1.pdf" / "invoice_2.pdf" or "IMG_001.jpg" /
# "IMG_002.jpg" -- the single most common way a batch of similarly-named
# unclassified files actually varies. Deliberately simple and disclosed as
# such: this does NOT recognize e.g. month names ("invoice_jan.pdf" vs
# "invoice_feb.pdf") as a shared pattern -- that would need real semantic
# understanding, which is exactly the AI's job for the group's *content*,
# not this deterministic, explainable grouping step. See Phase 7 of the
# spec this feature implements: "prefer deterministic grouping... the AI
# should help interpret the group, not become an autonomous classifier."
_TRAILING_NUMBER_RE = re.compile(r"[-_ ]?\d+$")


def _group_key(filename: str) -> tuple[str, str]:
    stem = Path(filename).stem
    ext = Path(filename).suffix.lower()
    normalized = _TRAILING_NUMBER_RE.sub("", stem).strip().lower() or stem.lower()
    return normalized, ext


def group_unclassified_files(no_match_items: list[dict], max_groups: int) -> tuple[list[dict], bool]:
    """Deterministic, filename-only grouping -- no AI call, no second
    classifier. Returns (groups, batch_limited); each group carries every
    file_name that shares its key so a single AI suggestion (and, if
    accepted, a single created rule) can cover all of them at once instead
    of asking about "invoice_1.pdf", "invoice_2.pdf", "invoice_3.pdf" one at
    a time. Order preserved (first-seen group first) so which groups get
    dropped under the batch cap is deterministic, not random."""
    groups: dict[tuple[str, str], list[dict]] = {}
    order: list[tuple[str, str]] = []
    for item in no_match_items:
        key = _group_key(item["filename"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)

    result = []
    for key in order:
        members = groups[key]
        representative = members[0]
        result.append(
            {
                "group_key": f"{key[0]}{key[1]}",
                "file_names": [m["filename"] for m in members],
                "files_affected": len(members),
                "representative_filename": representative["filename"],
                "extension": Path(representative["filename"]).suffix.lower(),
                "size_bytes": representative.get("file_size", 0),
            }
        )

    batch_limited = len(result) > max_groups
    return result[:max_groups], batch_limited


def _build_suggestion_prompt(groups: list[dict]) -> str:
    # Only safe metadata ever leaves this process for the AI provider --
    # never source_path/destination_path (which would reveal real
    # filesystem layout), never file content. See ai_provider.py's
    # SUGGESTION_SYSTEM_PROMPT for what the model is told this shape means.
    payload = [
        {
            "group_index": i,
            "filename": g["representative_filename"],
            "extension": g["extension"],
            "size_bytes": g["size_bytes"],
            "files_affected": g["files_affected"],
        }
        for i, g in enumerate(groups)
    ]
    return json.dumps(payload)


def _safe_str(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _build_suggestion(group: dict, raw: dict | None, watch_root: Path) -> UnclassifiedSuggestion:
    base = dict(
        group_key=group["group_key"],
        file_names=group["file_names"],
        files_affected=group["files_affected"],
    )

    if not isinstance(raw, dict):
        # Missing/malformed entry for this specific group_index -- never
        # lets one bad or absent group entry take down every other group's
        # suggestion (see generate_unclassified_suggestions' own per-group
        # loop below).
        return UnclassifiedSuggestion(
            **base,
            suggestion_status="unavailable",
            message="Couldn't generate a suggestion for these files -- try again.",
        )

    status = raw.get("status")

    if status == "needs_clarification":
        return UnclassifiedSuggestion(
            **base,
            suggestion_status="needs_clarification",
            message=_safe_str(raw.get("message"))
            or "Filename and extension don't provide enough information to suggest a rule.",
        )

    if status == "unsupported":
        return UnclassifiedSuggestion(
            **base,
            suggestion_status="unsupported",
            message=_safe_str(raw.get("message"))
            or "No supported FileFlow rule type fits these files.",
        )

    if status not in ("ready", "low_confidence"):
        return UnclassifiedSuggestion(
            **base,
            suggestion_status="unavailable",
            message="Couldn't generate a suggestion for these files -- try again.",
        )

    category = _safe_str(raw.get("suggested_category"))
    reason = [r for r in (raw.get("reason") or []) if isinstance(r, str) and r.strip()]

    suggested_rule = None
    destination = None
    rule_raw = raw.get("suggested_rule")
    if isinstance(rule_raw, dict):
        try:
            candidate = AIRuleProposal.model_validate({**rule_raw, "name": rule_raw.get("name") or category or ""})
        except ValidationError:
            candidate = None
        if candidate is not None:
            # The exact same field-by-field validation an AI Rule Generator
            # proposal goes through (services/ai_rule_service.py) -- schema
            # checks, KeywordRule/RegexRule/DateRule, ReDoS protection, and
            # is_within_watch_folder on the destination. A suggestion is
            # never shown as usable ("ready") on the strength of the AI's
            # own claim alone.
            validated = _validate_candidate(candidate, watch_root)
            if validated.status == "ready" and validated.proposal is not None:
                suggested_rule = validated.proposal
                destination = validated.proposal.destination

    if status == "ready" and suggested_rule is None:
        # The model said "ready" but gave no usable rule, or one that
        # failed the exact same validation a manual/Feature-3 rule would --
        # never shown as a confident, actionable suggestion.
        return UnclassifiedSuggestion(
            **base,
            suggestion_status="invalid",
            suggested_category=category,
            reason=reason,
            message="Couldn't build a valid rule from this suggestion.",
        )

    return UnclassifiedSuggestion(
        **base,
        suggestion_status=status,
        suggested_category=category,
        suggested_destination=destination,
        reason=reason,
        suggested_rule=suggested_rule,
    )


def _find_preview_command(db, user_id: int, command_id: int) -> dict | None:
    """A preview_organize_existing command belonging to this account only
    (scoped by user_id, so one account can never read another's
    agent-discovered file list) -- None if it doesn't exist, isn't this
    account's, or isn't that command type."""
    return db.agent_commands.find_one(
        {"_id": command_id, "user_id": user_id, "type": "preview_organize_existing"}
    )


def generate_unclassified_suggestions(
    db, user: dict, command_id: int | None
) -> UnclassifiedSuggestionResult | None:
    """Local accounts: scans the watch folder directly (plan_organize_
    existing -- the exact same discovery Organization Preview already uses,
    never a second scanner). Agent-connected accounts have no other way to
    see the agent's own filesystem, so this reuses Organization Preview's
    existing "preview_organize_existing" agent command for discovery rather
    than inventing a new one: the first call (command_id is None) just
    enqueues that command and returns queued=True; once the browser has
    polled GET /api/agent-commands (existing, generic) for that command's
    completion, a second call with command_id looks up its already-stored
    result and runs suggestions against it. The AI call itself always
    happens here, on the backend -- the agent only ever reports plain file
    metadata, never sees or calls the AI provider itself.

    Returns None only for a command_id that isn't a real, completed,
    account-owned preview_organize_existing command -- routes.py turns that
    into a 404, same as agent_routes.py's own "Unknown command." precedent."""
    watch_root = Path(user["watch_folder"])

    if is_agent_connected(user):
        if command_id is None:
            command = enqueue_agent_command(db, user["id"], "preview_organize_existing", {})
            return UnclassifiedSuggestionResult(queued=True, command_id=command["id"])
        command = _find_preview_command(db, user["id"], command_id)
        if command is None:
            return None
        if command.get("status") != "done":
            # Found, but not done yet -- still queued, not an error; the
            # browser keeps polling the same way Organization Preview does.
            return UnclassifiedSuggestionResult(queued=True, command_id=command_id)
        items = (command.get("result") or {}).get("items", [])
    else:
        items = plan_organize_existing(db, user)

    total = len(items)
    no_match_items = [i for i in items if i.get("status") == "no_match"]
    unclassified = len(no_match_items)

    if not no_match_items:
        return UnclassifiedSuggestionResult(total=total, unclassified=0, suggestions=[])

    groups, batch_limited = group_unclassified_files(
        no_match_items, settings.AI_UNCLASSIFIED_MAX_BATCH_SIZE
    )

    try:
        raw_results = generate_suggestion_completion(_build_suggestion_prompt(groups))
    except AIProviderError as exc:
        logger.warning("AI provider failure while generating unclassified suggestions: %s", exc)
        return UnclassifiedSuggestionResult(
            total=total,
            unclassified=unclassified,
            suggestions=[],
            batch_limited=batch_limited,
            message=UNAVAILABLE_MESSAGE,
        )

    by_index: dict[int, dict] = {}
    for entry in raw_results:
        if isinstance(entry, dict) and isinstance(entry.get("group_index"), int):
            by_index[entry["group_index"]] = entry

    suggestions = [
        _build_suggestion(group, by_index.get(i), watch_root) for i, group in enumerate(groups)
    ]

    return UnclassifiedSuggestionResult(
        total=total,
        unclassified=unclassified,
        suggestions=suggestions,
        batch_limited=batch_limited,
    )
