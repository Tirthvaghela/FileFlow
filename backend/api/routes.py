import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from api.auth import get_current_user
from automation.organizer import (
    claim_undoable_log,
    generate_simulated_download,
    organize_existing_files,
    reclassify_file,
    undo_last_operation,
)
from config.agent_release import AGENT_RELEASE_PATH
from config.onboarding_templates import ONBOARDING_TEMPLATES
from config.settings import all_watch_folders, paths_overlap, resolve_watch_folder, settings
from database.db import get_db
from models.models import Document
from models.schemas import (
    ActivityLogOut,
    AdditionalWatchFolderRequest,
    CategorySizeStat,
    DigestResult,
    FolderPickOut,
    OnboardingTemplateOut,
    OrganizeExistingResult,
    ReclassifyRequest,
    ReclassifyResult,
    RulePreviewOut,
    RulePreviewRequest,
    RulesOut,
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
from services.digest_service import send_weekly_digest
from services.report_service import build_csv, build_excel, build_pdf
from services.agent_service import enqueue_agent_command, is_agent_connected
from services.rule_preview_service import preview_rule
from services.stats_service import get_category_sizes, get_stats, get_weekly_reports

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


@router.get("/stats", response_model=StatsOut)
def stats(db=Depends(get_db), user=Depends(get_current_user)):
    return get_stats(db, user["id"])


@router.get("/categories", response_model=list[CategorySizeStat])
def categories(db=Depends(get_db), user=Depends(get_current_user)):
    return get_category_sizes(db, user["id"])


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
    path, for instance."""
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


@router.post("/rules/preview", response_model=RulePreviewOut)
def rules_preview(
    request: RulePreviewRequest, db=Depends(get_db), user=Depends(get_current_user)
):
    """Read-only: shows which already-organized files a not-yet-saved rule
    would have matched. Never touches the filesystem or rules.json."""
    return preview_rule(db, user["id"], request.type, request.match)


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

        enqueue_agent_command(
            db,
            user["id"],
            "reclassify",
            {"log_id": log_id, "source_path": log.destination_path, "category": category},
        )
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
        enqueue_agent_command(db, user["id"], "organize_existing", {})
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
    show it without waiting for the scheduled weekly run. Requires
    SMTP_USERNAME/SMTP_PASSWORD to be set; otherwise reports back that it
    was skipped."""
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        return DigestResult(success=False, message="Email sending is not configured.")
    sent = send_weekly_digest(db, user)
    if sent:
        return DigestResult(success=True, message=f"Digest sent to {user['email']}.")
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
