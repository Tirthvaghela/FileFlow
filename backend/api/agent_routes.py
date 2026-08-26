import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.auth import get_current_agent, require_full_agent_scope
from automation.organizer import release_undo_claim
from config.agent_release import (
    AGENT_LATEST_VERSION,
    AGENT_RELEASE_PATH,
    agent_release_sha256,
)
from database.db import get_db, insert_with_id
from models.models import Document, new_activity_log
from models.schemas import (
    ActivityLogOut,
    AgentActivityIn,
    AgentCommandCompleteIn,
    AgentCommandOut,
    AgentVersionOut,
    RulesOut,
)
from rules.rule_engine import get_rule_engine
from api.websocket_manager import manager

logger = logging.getLogger("fileflow.agent_routes")

# Every route here is authenticated by a long-lived bearer token (see
# api/auth.get_current_agent), not the browser's session cookie -- this is
# the API surface a background process on a user's own machine talks to,
# entirely separate from the web dashboard.
router = APIRouter(prefix="/api/agent", dependencies=[Depends(get_current_agent)])


def _touch_heartbeat(db, user_id: int) -> None:
    db.users.update_one(
        {"_id": user_id}, {"$set": {"agent_last_seen_at": datetime.now(timezone.utc)}}
    )


@router.get("/rules", response_model=RulesOut)
def get_rules_for_agent(db=Depends(get_db), user=Depends(get_current_agent)):
    _touch_heartbeat(db, user["id"])
    engine = get_rule_engine(db, user["id"], Path(user["watch_folder"]))
    return engine.rules


@router.post("/activity", response_model=ActivityLogOut)
async def report_activity(
    body: AgentActivityIn, db=Depends(get_db), user=Depends(require_full_agent_scope)
):
    """The agent performed a move on its own machine and is reporting the
    result -- this is the exact same insert + broadcast process_file()
    does for a locally-watched file, just reachable remotely, so the web
    dashboard updates live regardless of which machine actually moved the
    file. async (unlike every other route in this file) specifically so
    the broadcast can be awaited directly on the request's own event loop
    -- no cross-thread asyncio.run_coroutine_threadsafe dance needed, that
    is only required from the watcher's own background thread.

    If client_ref matches a row already recorded for this user, this is a
    retried delivery (the agent's outbox never saw a successful response
    even though the insert+broadcast below already happened once) -- just
    return the existing row rather than inserting a duplicate and
    double-broadcasting it to the live dashboard."""
    if body.client_ref is not None:
        existing = db.activity_log.find_one(
            {"user_id": user["id"], "client_ref": body.client_ref}
        )
        if existing:
            return existing

    log = insert_with_id(
        db,
        "activity_log",
        new_activity_log(user_id=user["id"], **body.model_dump()),
    )
    payload = ActivityLogOut.model_validate(log).model_dump(mode="json")
    await manager.broadcast(payload, user["id"])
    return log


@router.get("/commands", response_model=list[AgentCommandOut])
def get_pending_commands(db=Depends(get_db), user=Depends(require_full_agent_scope)):
    _touch_heartbeat(db, user["id"])
    docs = db.agent_commands.find({"user_id": user["id"], "status": "pending"}).sort("_id", 1)
    return [AgentCommandOut(id=d["id"], type=d["type"], payload=d["payload"]) for d in docs]


@router.post("/commands/{command_id}/complete")
def complete_command(
    command_id: int,
    body: AgentCommandCompleteIn,
    db=Depends(get_db),
    user=Depends(require_full_agent_scope),
):
    command = db.agent_commands.find_one({"_id": command_id, "user_id": user["id"]})
    if not command:
        raise HTTPException(status_code=404, detail="Unknown command.")

    if command["type"] == "undo" and not body.success:
        # The agent couldn't actually move the file back -- release the
        # claim undo_last_operation took when this command was enqueued,
        # so the entry stays visible as undoable for a retry instead of
        # silently vanishing from history with nothing to show for it.
        log_id = command["payload"].get("log_id")
        if log_id is not None:
            release_undo_claim(db, log_id)

    if command["type"] == "organize_existing":
        # The agent's own scan/organize/duplicate/error counts -- otherwise
        # received here and discarded entirely (only reclassify's result is
        # used below), leaving no trace anywhere of whether a remote
        # scheduled or manual "organize existing files" run actually did
        # anything once the agent picked it up.
        result = body.result or {}
        logger.info(
            "organize_existing command %d for user %d completed: scanned %s, organized %s, "
            "%s duplicate(s), %s error(s).",
            command_id, user["id"],
            result.get("scanned"), result.get("organized"), result.get("duplicates"), result.get("errors"),
        )

    if command["type"] == "reclassify" and body.success:
        log_id = command["payload"].get("log_id")
        result = body.result or {}
        if log_id is not None and result.get("destination_path"):
            db.activity_log.update_one(
                {"_id": log_id},
                {
                    "$set": {
                        "category": command["payload"].get("category"),
                        "destination_path": result["destination_path"],
                        "final_filename": Path(result["destination_path"]).name,
                    }
                },
            )

    db.agent_commands.update_one(
        {"_id": command_id},
        {"$set": {"status": "done", "success": body.success, "error": body.error}},
    )
    return {"success": True}


@router.get("/version", response_model=AgentVersionOut)
def get_latest_agent_version():
    if not AGENT_RELEASE_PATH.exists():
        raise HTTPException(status_code=404, detail="No agent release published yet.")
    return AgentVersionOut(
        version=AGENT_LATEST_VERSION,
        sha256=agent_release_sha256(),
        download_url="/api/agent/download",
    )


@router.get("/download")
def download_agent_installer():
    if not AGENT_RELEASE_PATH.exists():
        raise HTTPException(status_code=404, detail="No agent release published yet.")
    return FileResponse(
        AGENT_RELEASE_PATH,
        filename=AGENT_RELEASE_PATH.name,
        media_type="application/octet-stream",
        # Same reasoning as the browser-facing counterpart in routes.py --
        # this URL serves different bytes as new versions ship, so nothing
        # (proxies included, not just browsers) should cache it.
        headers={"Cache-Control": "no-store"},
    )
