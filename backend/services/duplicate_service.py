"""Smart Duplicate Groups: finds files with EXACT (SHA-256) content
identity across an account's watch folders and explains them.

THIS FEATURE EXPLAINS DUPLICATES. IT NEVER DECIDES WHICH COPY TO KEEP, AND
NEVER DELETES, MOVES, RENAMES, OR REPLACES A FILE.

analyze_duplicates() below is the only entry point routes.py calls. It
never writes to activity_log or rules, and never touches a real file beyond
reading it (stat + streaming hash) -- purely read-only, advisory analysis.

Reuses automation.organizer.build_duplicate_groups_result() -- the exact
same discovery (is_ignored), hashing (compute_hash, the same streaming
SHA-256 primitive resolve_destination()'s own duplicate-collision check
already uses) and grouping logic the agent's own local scan uses
(agent/commands.py), so the two can never disagree about what counts as a
duplicate. This module only adds the DB-backed agent-connected two-call
dance and Pydantic wrapping -- no second hashing/grouping implementation."""

from automation.organizer import build_duplicate_groups_result
from config.settings import all_watch_folders, settings
from models.schemas import DuplicateAnalysisResult
from services.agent_service import enqueue_agent_command, is_agent_connected


def _find_duplicate_command(db, user_id: int, command_id: int) -> dict | None:
    """A duplicate_analysis command belonging to this account only (scoped
    by user_id, so one account can never read another's agent-discovered
    duplicate report) -- None if it doesn't exist, isn't this account's, or
    isn't that command type."""
    return db.agent_commands.find_one(
        {"_id": command_id, "user_id": user_id, "type": "duplicate_analysis"}
    )


def analyze_duplicates(db, user: dict, command_id: int | None) -> DuplicateAnalysisResult | None:
    """Local accounts: scans every one of the account's watch folders
    directly (backend has real filesystem access). Agent-connected
    accounts have no other way to see the agent's own filesystem, so this
    reuses the existing generic agent command mechanism (enqueue_agent_
    command/GET /api/agent-commands, same as Organization Preview and AI
    Unclassified Suggestions) with a new "duplicate_analysis" command type:
    the first call (command_id is None) enqueues it and returns
    queued=True; once the browser has polled for that command's
    completion, a second call with command_id looks up its already-stored
    result. The backend never attempts to touch the agent's filesystem
    itself -- only the agent ever reads/hashes its own local files.

    Returns None only for a command_id that isn't a real, completed,
    account-owned duplicate_analysis command -- routes.py turns that into
    a 404, same as the other agent-backed features' precedent."""
    if is_agent_connected(user):
        if command_id is None:
            command = enqueue_agent_command(db, user["id"], "duplicate_analysis", {})
            return DuplicateAnalysisResult(queued=True, command_id=command["id"])
        command = _find_duplicate_command(db, user["id"], command_id)
        if command is None:
            return None
        if command.get("status") != "done":
            # Found, but not done yet -- still queued, not an error; the
            # browser keeps polling the same way the other agent-backed
            # features do.
            return DuplicateAnalysisResult(queued=True, command_id=command_id)
        return DuplicateAnalysisResult(**(command.get("result") or {}))

    raw = build_duplicate_groups_result(
        all_watch_folders(user), settings.DUPLICATE_ANALYSIS_MAX_GROUPS_RETURNED
    )
    return DuplicateAnalysisResult(**raw)
