import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pymongo.errors import DuplicateKeyError

from api.auth import get_current_user
from automation.organizer import (
    claim_undoable_log,
    claim_undoable_log_by_id,
    delete_category_file,
    generate_simulated_download,
    list_category_files,
    list_category_stats,
    organize_existing_files,
    reclassify_file,
    undo_last_operation,
    undo_specific_operation,
)
from config.agent_release import AGENT_RELEASE_PATH
from config.onboarding_templates import ONBOARDING_TEMPLATES
from config.settings import all_watch_folders, paths_overlap, resolve_watch_folder
from database.db import get_db
from models.models import Document
from models.schemas import (
    ActivityLogOut,
    AdditionalWatchFolderRequest,
    AgentCommandHistoryOut,
    CategoryFileDeleteRequest,
    CategoryFileOut,
    CategorySizeStat,
    DeleteResult,
    DigestResult,
    FolderPickOut,
    OnboardingTemplateOut,
    OrganizeExistingResult,
    ReclassifyRequest,
    ReclassifyResult,
    RulePreviewOut,
    RulePreviewRequest,
    RulesOut,
    RuleSimulationResult,
    StatsOut,
    UndoResult,
    WatchFolderOut,
    WatchFolderUpdate,
    WatchFoldersOut,
    WeeklyReportStat,
)
from monitor.watcher import add_additional_watch, remove_additional_watch, update_watch_folder
from rules.classifier import is_within_watch_folder
from rules.rule_engine import get_rule_engine
from services.digest_service import DigestOutcome, send_weekly_digest
from services.report_service import build_csv, build_excel, build_pdf
from services.agent_service import enqueue_agent_command, is_agent_connected
from services.rule_preview_service import preview_rule
from services.rule_simulation_service import simulate_rules
from services.stats_service import get_stats, get_weekly_reports

# Every route on this router requires a valid session -- /api/health and
# /api/auth/* live on separate, unauthenticated routers (see main.py and
# auth_routes.py) since they must be reachable before login.
router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


@router.get("/logs", response_model=list[ActivityLogOut])
def list_logs(limit: int = 50, db=Depends(get_db), user=Depends(get_current_user)):
    logs = (
        db.activity_log.find({"user_id": user["id"]}).sort("_id", -1).limit(min(limit, 500))
    )
    return list(logs)


@router.get("/agent-commands", response_model=list[AgentCommandHistoryOut])
def list_agent_commands(
    limit: int = 20,
    type: str | None = None,
    source: str | None = None,
    log_id: int | None = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Recent agent command activity (undo/reclassify/organize_existing),
    newest first -- the browser-facing counterpart to GET /api/agent/commands
    (agent_routes.py), which only ever returns the calling agent's own
    still-pending work. user_id comes from the authenticated session only,
    never a client-supplied value, so one account can never see another's
    command history no matter what's passed in the query string.

    `source` filters on payload.source ("scheduled" vs "manual" -- see
    archive_scheduler.py's and this module's own organize_existing route,
    the only two places that set it). `log_id` filters on payload.log_id
    (undo/reclassify only -- History uses it to correlate a specific row
    with the command it triggered). Neither filter, nor the response's own
    log_id field below, ever exposes the rest of the raw payload --
    AgentCommandHistoryOut deliberately omits everything else in it."""
    query: dict = {"user_id": user["id"]}
    if type is not None:
        query["type"] = type
    if source is not None:
        query["payload.source"] = source
    if log_id is not None:
        query["payload.log_id"] = log_id
    docs = db.agent_commands.find(query).sort("_id", -1).limit(min(limit, 100))
    results = []
    for doc in docs:
        doc["log_id"] = doc.get("payload", {}).get("log_id")
        results.append(doc)
    return results


@router.get("/stats", response_model=StatsOut)
def stats(db=Depends(get_db), user=Depends(get_current_user)):
    return get_stats(db, user["id"])


@router.get("/categories", response_model=list[CategorySizeStat])
def categories(db=Depends(get_db), user=Depends(get_current_user)):
    """A live count/size per category folder, sourced the same way as
    GET /api/categories/{category}/files -- so a category tile here always
    agrees with what its own detail page shows, including disappearing once
    every file that was ever organized into it is gone."""
    engine = get_rule_engine(db, user["id"], Path(user["watch_folder"]))
    return list_category_stats(user, engine.archive_folder)


@router.get("/categories/{category}/files", response_model=list[CategoryFileOut])
def get_category_files(category: str, user=Depends(get_current_user)):
    """A live listing of what's actually sitting in this category folder
    right now, sorted largest-first by default -- the frontend re-sorts
    client-side, but a sensible default matters for whoever's here to find
    what's eating space."""
    files = list_category_files(user, category)
    files.sort(key=lambda f: f["size_bytes"], reverse=True)
    return files


@router.delete("/categories/{category}/files", response_model=DeleteResult)
def delete_category_file_route(
    category: str,
    body: CategoryFileDeleteRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    if is_agent_connected(user):
        # The real folder lives on the agent's own machine, not necessarily
        # this backend's -- deleting a same-named path here could do
        # nothing, or worse, delete an unrelated file that happens to exist
        # at that path on the backend's machine. Refusing cleanly beats
        # guessing at a command the agent doesn't support yet.
        return DeleteResult(
            success=False,
            message="Deleting files isn't supported yet for accounts with a connected agent.",
        )
    success, message = delete_category_file(db, user, category, body.path)
    return DeleteResult(success=success, message=message)


@router.get("/rules", response_model=RulesOut)
def get_rules(db=Depends(get_db), user=Depends(get_current_user)):
    engine = get_rule_engine(db, user["id"], Path(user["watch_folder"]))
    return engine.rules


@router.put("/rules", response_model=RulesOut)
def update_rules(new_rules: RulesOut, db=Depends(get_db), user=Depends(get_current_user)):
    engine = get_rule_engine(db, user["id"], Path(user["watch_folder"]))
    engine.save(new_rules.model_dump())
    return engine.rules


@router.get("/onboarding/templates", response_model=list[OnboardingTemplateOut])
def list_onboarding_templates():
    return [
        OnboardingTemplateOut(id=template_id, label=template["label"], description=template["description"])
        for template_id, template in ONBOARDING_TEMPLATES.items()
    ]


@router.post("/onboarding/templates/{template_id}/apply", response_model=RulesOut)
def apply_onboarding_template(
    template_id: str, db=Depends(get_db), user=Depends(get_current_user)
):
    template = ONBOARDING_TEMPLATES.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Unknown starter template: {template_id!r}")
    engine = get_rule_engine(db, user["id"], Path(user["watch_folder"]))
    engine.save(template["rules"])
    return engine.rules


@router.post("/settings/browse-folder", response_model=FolderPickOut)
def browse_for_folder():
    """Opens a native Windows folder picker on the machine running the
    backend, so picking a watch folder doesn't require typing or
    copy-pasting an absolute path. Only meaningful because this is a local
    setup where the backend and the browser run on the same machine --
    there's no browser API that hands JS a real filesystem path (the File
    System Access API deliberately withholds it). A plain `def` (not
    `async def`) so FastAPI runs it in its worker threadpool instead of on
    the event loop -- the dialog blocks until the user picks a folder or
    cancels, and nothing else (the live activity websocket, other
    requests) should have to wait on that.

    Returns path=None if the user cancels rather than erroring -- that's
    not a failure, just "no change"."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        chosen = filedialog.askdirectory(parent=root, title="Choose a folder for FileFlow to watch")
    finally:
        root.destroy()
    return FolderPickOut(path=chosen or None)


def _check_folder_available(db, resolved: Path, user_id: int, ignore: Path | None = None) -> None:
    """Raises if `resolved` overlaps any folder anyone is already
    watching -- including this same account's OTHER folders, not just
    other accounts'. Exact-match alone isn't enough: pointing a watch
    folder at a subfolder of another tree (or vice versa) exposes/hijacks
    those files just as effectively as an exact collision would, since the
    watcher and organize-existing both operate on whatever folder they're
    pointed at, recursively. `ignore` is the one folder allowed to
    "overlap" itself -- the primary folder being replaced by the same
    path, for instance.

    This is the only boundary enforced on a chosen watch folder -- there
    is no check against any operator-defined root, by design (see
    resolve_watch_folder's docstring, config/settings.py)."""
    for other in db.users.find({}, {"id": 1, "watch_folder": 1, "additional_watch_folders": 1}):
        for folder in all_watch_folders(other):
            if ignore is not None and folder == ignore and other["id"] == user_id:
                continue
            if paths_overlap(resolved, folder):
                if other["id"] == user_id:
                    raise HTTPException(
                        status_code=400,
                        detail="This overlaps a folder you're already watching.",
                    )
                raise HTTPException(
                    status_code=400,
                    detail="Another account's watch folder overlaps with that path.",
                )


@router.put("/settings/watch-folder", response_model=WatchFolderOut)
def update_watch_folder_route(
    body: WatchFolderUpdate, db=Depends(get_db), user=Depends(get_current_user)
):
    path = body.path.strip()
    if not path:
        raise HTTPException(status_code=400, detail="Folder path can't be empty.")
    try:
        resolved = resolve_watch_folder(path)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Can't use that folder: {exc}")

    _check_folder_available(db, resolved, user["id"], ignore=Path(user["watch_folder"]))

    db.users.update_one({"_id": user["id"]}, {"$set": {"watch_folder": str(resolved)}})
    update_watch_folder(user["id"], resolved)
    return WatchFolderOut(watch_folder=str(resolved))


@router.post("/settings/watch-folders", response_model=WatchFoldersOut)
def add_additional_watch_folder_route(
    body: AdditionalWatchFolderRequest, db=Depends(get_db), user=Depends(get_current_user)
):
    """Adds an extra folder this account watches alongside its primary
    one -- same rules, organized independently. See
    config.settings.all_watch_folders."""
    path = body.path.strip()
    if not path:
        raise HTTPException(status_code=400, detail="Folder path can't be empty.")
    try:
        resolved = resolve_watch_folder(path)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Can't use that folder: {exc}")

    _check_folder_available(db, resolved, user["id"])

    db.users.update_one({"_id": user["id"]}, {"$addToSet": {"additional_watch_folders": str(resolved)}})
    add_additional_watch(user["id"], resolved)
    updated = db.users.find_one({"_id": user["id"]})
    return WatchFoldersOut(
        watch_folder=updated["watch_folder"],
        additional_watch_folders=updated.get("additional_watch_folders", []),
    )


@router.delete("/settings/watch-folders", response_model=WatchFoldersOut)
def remove_additional_watch_folder_route(
    body: AdditionalWatchFolderRequest, db=Depends(get_db), user=Depends(get_current_user)
):
    db.users.update_one({"_id": user["id"]}, {"$pull": {"additional_watch_folders": body.path}})
    remove_additional_watch(user["id"], Path(body.path))
    updated = db.users.find_one({"_id": user["id"]})
    return WatchFoldersOut(
        watch_folder=updated["watch_folder"],
        additional_watch_folders=updated.get("additional_watch_folders", []),
    )


@router.post("/undo", response_model=UndoResult)
def undo(db=Depends(get_db), user=Depends(get_current_user)):
    if is_agent_connected(user):
        # Same atomic claim undo_last_operation uses -- only the *move*
        # is different (queued for the agent instead of done here), the
        # concurrency guarantee against a double-click has to be identical.
        log = claim_undoable_log(db, user["id"])
        if log is None:
            return UndoResult(success=False, message="No undoable operation found.")
        enqueue_agent_command(
            db,
            user["id"],
            "undo",
            {
                "log_id": log["id"],
                "source_path": log.source_path,
                "destination_path": log.destination_path,
            },
        )
        return UndoResult(
            success=True, message="Queued -- your agent will pick this up shortly.", queued=True
        )

    success, message, log = undo_last_operation(db, user)
    return UndoResult(success=success, message=message, log=log)


@router.post("/logs/{log_id}/undo", response_model=UndoResult)
def undo_log(log_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    """Same as /undo, but targets one specific row a user picked from
    History instead of always whichever is most recent -- every row gets
    its own working Undo button, not just the latest one."""
    if is_agent_connected(user):
        log = claim_undoable_log_by_id(db, user["id"], log_id)
        if log is None:
            return UndoResult(success=False, message="That operation can't be undone.")
        enqueue_agent_command(
            db,
            user["id"],
            "undo",
            {
                "log_id": log["id"],
                "source_path": log.source_path,
                "destination_path": log.destination_path,
            },
        )
        return UndoResult(
            success=True, message="Queued -- your agent will pick this up shortly.", queued=True
        )

    success, message, log = undo_specific_operation(db, user, log_id)
    return UndoResult(success=success, message=message, log=log)


@router.post("/rules/preview", response_model=RulePreviewOut)
def rules_preview(
    request: RulePreviewRequest, db=Depends(get_db), user=Depends(get_current_user)
):
    """Read-only: shows which already-organized files a not-yet-saved rule
    would have matched. Never touches the filesystem or rules.json."""
    return preview_rule(db, user["id"], request.type, request.match)


@router.post("/rules/simulate", response_model=RuleSimulationResult)
def rules_simulate(
    candidate_rules: RulesOut, db=Depends(get_db), user=Depends(get_current_user)
):
    """Read-only dry-run: re-classifies recent history against a full
    not-yet-saved rule set (the same shape PUT /api/rules accepts) and
    reports which files would now land somewhere different. Never calls
    RuleEngine.save() or touches a file."""
    return simulate_rules(db, user, candidate_rules.model_dump())


@router.post("/logs/{log_id}/reclassify", response_model=ReclassifyResult)
def reclassify(
    log_id: int,
    request: ReclassifyRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    if is_agent_connected(user):
        raw = db.activity_log.find_one({"_id": log_id, "user_id": user["id"]})
        if not raw:
            return ReclassifyResult(success=False, message="That entry can't be reclassified.")
        log = Document(raw)
        if log.undone or not log.destination_path:
            return ReclassifyResult(success=False, message="That entry can't be reclassified.")

        category = request.category.strip()
        watch_root = Path(user["watch_folder"])
        if not category or not is_within_watch_folder(category, watch_root):
            return ReclassifyResult(success=False, message="Invalid destination category.")

        try:
            enqueue_agent_command(
                db,
                user["id"],
                "reclassify",
                {"log_id": log_id, "source_path": log.destination_path, "category": category},
            )
        except DuplicateKeyError:
            # A pending reclassify command for this exact row already
            # exists (the partial unique index in database/db.py catching
            # a concurrent duplicate request) -- it will still be picked up
            # and processed, so this is still an accurate "queued", not a
            # failure.
            pass
        return ReclassifyResult(
            success=True, message="Queued -- your agent will pick this up shortly.", queued=True
        )

    success, message, log = reclassify_file(log_id, request.category, db, user)
    return ReclassifyResult(success=success, message=message, log=log)


@router.post("/organize-existing", response_model=OrganizeExistingResult)
def organize_existing(db=Depends(get_db), user=Depends(get_current_user)):
    """One-time sweep of files already sitting in the watch folder root,
    e.g. everything downloaded before FileFlow started watching."""
    if is_agent_connected(user):
        # source: "manual" mirrors archive_scheduler.py's own "scheduled"
        # tag on the exact same command type -- the only thing that tells
        # the recent-activity view apart which one triggered this run.
        enqueue_agent_command(db, user["id"], "organize_existing", {"source": "manual"})
        return OrganizeExistingResult(queued=True)
    return organize_existing_files(db, user)


@router.get("/simulate-download")
def simulate_download(user=Depends(get_current_user)):
    """Serve a small demo file as a genuine download -- it lands wherever
    the browser saves downloads (typically the same folder FileFlow is
    already watching), so the live pipeline picks it up exactly like any
    real download, instead of the backend writing straight into the watch
    folder itself."""
    filename, data, media_type = generate_simulated_download()
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/settings/agent-installer")
def download_agent_installer():
    """Cookie-authed counterpart to /api/agent/download (which requires an
    agent bearer token, meant for the agent process itself) -- lets a
    signed-in browser user download the same installer straight from the
    dashboard's navbar, without needing to mint an agent token just to
    fetch the .exe."""
    if not AGENT_RELEASE_PATH.exists():
        raise HTTPException(status_code=404, detail="No agent release published yet.")
    return FileResponse(
        AGENT_RELEASE_PATH,
        filename=AGENT_RELEASE_PATH.name,
        media_type="application/octet-stream",
        # This exact URL keeps serving a newer file every time a release
        # ships, but FileResponse sets no Cache-Control by default -- with
        # only Last-Modified/ETag to go on, Chrome happily reused its
        # cached copy of an old version on repeat clicks (verified
        # directly: a user kept getting 1.0.3 from this route long after
        # the server itself had 1.0.4 on disk). no-store forces a fresh
        # fetch every time.
        headers={"Cache-Control": "no-store"},
    )


@router.get("/reports/weekly", response_model=list[WeeklyReportStat])
def weekly_reports(weeks: int = 4, db=Depends(get_db), user=Depends(get_current_user)):
    return get_weekly_reports(db, user["id"], weeks=min(weeks, 26))


@router.post("/reports/send-digest", response_model=DigestResult)
def send_digest(db=Depends(get_db), user=Depends(get_current_user)):
    """Manually trigger the weekly email digest on demand -- lets a demo
    show it without waiting for the scheduled weekly run. send_weekly_
    digest() itself now distinguishes every reason it might not actually
    send (nothing to report this week, SMTP not configured, or a real
    send failure) instead of a bare bool, so this response can say which
    one actually happened rather than a single generic failure message."""
    outcome = send_weekly_digest(db, user)
    if outcome == DigestOutcome.SENT:
        return DigestResult(success=True, message=f"Digest sent to {user['email']}.")
    if outcome == DigestOutcome.SKIPPED_NO_ACTIVITY:
        return DigestResult(
            success=False, message="No activity to report this week -- nothing was sent."
        )
    if outcome == DigestOutcome.SKIPPED_SMTP_NOT_CONFIGURED:
        return DigestResult(success=False, message="Email sending is not configured.")
    return DigestResult(success=False, message="Failed to send the digest -- check server logs.")


@router.get("/reports/csv")
def export_csv(
    since: str | None = None,
    until: str | None = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc) if since else None
    until_dt = (
        datetime.fromisoformat(until).replace(tzinfo=timezone.utc) + timedelta(days=1)
        if until
        else None
    )
    content = build_csv(db, user["id"], since=since_dt, until=until_dt)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fileflow_report.csv"},
    )


@router.get("/reports/excel")
def export_excel(db=Depends(get_db), user=Depends(get_current_user)):
    content = build_excel(db, user["id"])
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=fileflow_report.xlsx"},
    )


@router.get("/reports/pdf")
def export_pdf(db=Depends(get_db), user=Depends(get_current_user)):
    content = build_pdf(db, user["id"])
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=fileflow_report.pdf"},
    )
