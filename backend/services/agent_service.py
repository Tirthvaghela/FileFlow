from datetime import datetime, timedelta, timezone

from database.db import insert_with_id

# How stale a heartbeat can be before an account is treated as "no agent
# connected" and routes fall back to today's direct local-filesystem
# behavior. The agent polls GET /api/agent/commands every few seconds, so
# 2 minutes comfortably covers a brief network hiccup without keeping a
# genuinely offline account stuck in "queued" mode for long.
AGENT_HEARTBEAT_TIMEOUT = timedelta(minutes=2)


def is_agent_connected(user: dict) -> bool:
    """True if this account has a remote agent that's checked in recently.
    Everything that used to act directly on the local filesystem (undo,
    reclassify, organize-existing) branches on this: agent-connected means
    only the agent can actually touch the file, so the action is queued for
    it instead of executed here."""
    last_seen = user.get("agent_last_seen_at")
    if not last_seen:
        return False
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_seen < AGENT_HEARTBEAT_TIMEOUT


def enqueue_agent_command(db, user_id: int, command_type: str, payload: dict) -> dict:
    return insert_with_id(
        db,
        "agent_commands",
        {
            "user_id": user_id,
            "type": command_type,
            "payload": payload,
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
        },
    )
