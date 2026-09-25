"""Natural Language File Search: a short natural-language request ->
AI-interpreted structured SearchQuery -> deterministic metadata search.

AI INTERPRETS WHAT THE USER MEANS. THE DETERMINISTIC SEARCH ENGINE DECIDES
WHICH FILES ACTUALLY MATCH. AI IS NEVER THE SEARCH ENGINE.

interpret_query() below is the AI boundary: it receives ONLY the user's raw
search text (never a filename, path, hash, or any filesystem data) and
returns EITHER a validated models.schemas.SearchQuery or a non-"ready"
status -- never a file, a path, or a "result". run_file_search() is the only
entry point routes.py calls; it never writes to activity_log or rules, and
never moves/renames/deletes a file -- purely read-only.

Reuses automation.file_ops.search_files_by_query() -- the exact same
discovery (is_ignored), classification (classify_file_explained(), the same
function Features 1/2/4/5 already use), and duplicate-group lookup (Feature
6's build_duplicate_groups_result()) the agent's own local search uses, so
the two can never disagree about which files match. This module only adds
the AI interpretation step, SearchQuery validation, and the DB-backed
agent-connected two-call dance."""

import logging
from pathlib import Path

from pydantic import ValidationError

from automation.file_ops import _time_range_reason, search_files_by_query
from config.settings import all_watch_folders, settings
from models.schemas import FileSearchResponse, SearchQuery
from rules.rule_engine import get_rule_engine
from services.agent_service import enqueue_agent_command, is_agent_connected
from services.ai_provider import (
    AIProviderAuthError,
    AIProviderError,
    AIProviderMalformedResponse,
    AIProviderRateLimited,
    AIProviderUnavailable,
    generate_search_completion,
)

logger = logging.getLogger("fileflow.ai")

# A search request is a short sentence, not a document -- also bounds what's
# ever sent to the provider, same reasoning as AI Rule Generator's own limit.
MAX_PROMPT_LENGTH = 500

UNAVAILABLE_MESSAGE = "AI search interpretation is temporarily unavailable. Please try again shortly."
MALFORMED_MESSAGE = "The search request could not be interpreted."
UNSUPPORTED_MESSAGE = (
    "FileFlow Search only looks at file names, extensions, sizes, dates, and locations -- it "
    "doesn't read file contents, so it can't answer this kind of request."
)


def _interpret(prompt: str) -> FileSearchResponse | SearchQuery:
    """Returns a validated SearchQuery on success, or a non-"ready"
    FileSearchResponse (needs_clarification/unsupported/error/invalid)
    otherwise. Never returns anything AI-authored as an authoritative
    result -- only ever a query for the deterministic engine to run, or an
    explanation of why there isn't one yet."""
    prompt = (prompt or "").strip()
    if not prompt:
        return FileSearchResponse(status="invalid", message="Please describe what you're looking for.")
    if len(prompt) > MAX_PROMPT_LENGTH:
        return FileSearchResponse(
            status="invalid", message=f"That search is too long (max {MAX_PROMPT_LENGTH} characters)."
        )

    try:
        raw = generate_search_completion(prompt)
    except AIProviderRateLimited:
        return FileSearchResponse(
            status="error", message="AI search is busy right now. Please try again in a moment."
        )
    except AIProviderAuthError:
        # Never surfaced to the client -- a misconfigured/revoked key is an
        # operator problem, not something the requester did or needs to know.
        logger.error("AI provider authentication failed while interpreting a file search.")
        return FileSearchResponse(status="error", message=UNAVAILABLE_MESSAGE)
    except (AIProviderUnavailable, AIProviderMalformedResponse, AIProviderError) as exc:
        logger.warning("AI provider failure while interpreting a file search: %s", exc)
        return FileSearchResponse(status="error", message=UNAVAILABLE_MESSAGE)

    if not isinstance(raw, dict):
        return FileSearchResponse(status="error", message=MALFORMED_MESSAGE)

    ai_status = raw.get("status")

    if ai_status == "unsupported":
        message = raw.get("message")
        return FileSearchResponse(
            status="unsupported",
            message=message if isinstance(message, str) and message.strip() else UNSUPPORTED_MESSAGE,
        )

    if ai_status == "needs_clarification":
        message = raw.get("message")
        raw_questions = raw.get("questions")
        questions = (
            [q for q in raw_questions if isinstance(q, str) and q.strip()]
            if isinstance(raw_questions, list)
            else []
        )
        return FileSearchResponse(
            status="needs_clarification",
            message=message
            if isinstance(message, str) and message.strip()
            else "I need a bit more detail to run this search.",
            questions=questions,
        )

    if ai_status != "ready":
        return FileSearchResponse(status="error", message=MALFORMED_MESSAGE)

    try:
        return SearchQuery.model_validate(raw.get("query") or {})
    except ValidationError:
        return FileSearchResponse(status="error", message=MALFORMED_MESSAGE)


def _describe_query(query: SearchQuery) -> list[str]:
    """Deterministic, backend-generated description of a VALIDATED
    SearchQuery -- never the AI's own prose (Phase 14: an explanation of
    what will happen is computed the same way a per-result match reason
    is, never asked of the model)."""
    lines: list[str] = []
    for term in query.filename_contains:
        lines.append(f'Filename contains "{term}"')
    for ext in query.extension:
        lines.append(f"Extension is {ext}")
    for term in query.path_contains:
        lines.append(f'Location contains "{term}"')
    if query.size_min_mb is not None:
        lines.append(f"Size is at least {query.size_min_mb:g} MB")
    if query.size_max_mb is not None:
        lines.append(f"Size is at most {query.size_max_mb:g} MB")
    if query.time_range:
        lines.append(_time_range_reason(query.model_dump()))
    if query.category_contains:
        lines.append(f'Category contains "{query.category_contains}"')
    if query.rule_name_contains:
        lines.append(f'Matched by a rule containing "{query.rule_name_contains}"')
    if query.unclassified_only:
        lines.append("Currently unclassified only")
    if query.duplicate_only:
        lines.append("Part of a duplicate-content group only")
    if not lines:
        lines.append("Every file in your watch folder")
    return lines


def _find_search_command(db, user_id: int, command_id: int) -> dict | None:
    """A file_search command belonging to this account only (scoped by
    user_id, so one account can never read another's agent-discovered
    search result) -- None if it doesn't exist, isn't this account's, or
    isn't that command type."""
    return db.agent_commands.find_one({"_id": command_id, "user_id": user_id, "type": "file_search"})


def run_file_search(db, user: dict, prompt: str, command_id: int | None) -> FileSearchResponse | None:
    """Local accounts: searches every one of the account's watch folders
    directly. Agent-connected accounts have no other way to see the
    agent's own filesystem, so this reuses the existing generic agent
    command mechanism with a new "file_search" command type (Phase 18: no
    existing command carries a SearchQuery): first call interprets the
    query and enqueues it (the agent receives ONLY the validated
    SearchQuery, never the natural-language text or an AI provider);
    second call fetches the already-stored result.

    Returns None only for a command_id that isn't a real, completed,
    account-owned file_search command -- routes.py turns that into a 404,
    same as the other agent-backed features' precedent."""
    if command_id is not None and is_agent_connected(user):
        command = _find_search_command(db, user["id"], command_id)
        if command is None:
            return None
        interpretation = (command.get("payload") or {}).get("interpretation") or []
        if command.get("status") != "done":
            return FileSearchResponse(status="ready", queued=True, command_id=command_id, interpretation=interpretation)
        raw = command.get("result") or {}
        return FileSearchResponse(status="ready", interpretation=interpretation, **raw)

    interpreted = _interpret(prompt)
    if isinstance(interpreted, FileSearchResponse):
        return interpreted
    query = interpreted
    interpretation = _describe_query(query)

    if is_agent_connected(user):
        command = enqueue_agent_command(
            db, user["id"], "file_search", {"query": query.model_dump(), "interpretation": interpretation}
        )
        return FileSearchResponse(status="ready", queued=True, command_id=command["id"], interpretation=interpretation)

    watch_root = Path(user["watch_folder"])
    engine = get_rule_engine(db, user["id"], watch_root)
    raw = search_files_by_query(
        all_watch_folders(user), engine.rules, query.model_dump(), settings.FILE_SEARCH_MAX_RESULT_LIMIT
    )
    return FileSearchResponse(status="ready", interpretation=interpretation, **raw)
