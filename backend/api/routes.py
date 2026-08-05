import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.auth import get_current_user
from automation.organizer import (
    create_simulated_download,
    organize_existing_files,
    reclassify_file,
    undo_last_operation,
)
from config.settings import resolve_watch_folder, settings
from database.db import get_db
from models.schemas import (
    ActivityLogOut,
    CategorySizeStat,
    DigestResult,
    OrganizeExistingResult,
    ReclassifyRequest,
    ReclassifyResult,
    RulePreviewOut,
    RulePreviewRequest,
    RulesOut,
    SimulateDownloadResult,
    StatsOut,
    UndoResult,
    WatchFolderOut,
    WatchFolderUpdate,
    WeeklyReportStat,
)
from monitor.watcher import update_watch_folder
from rules.rule_engine import get_rule_engine
from services.digest_service import send_weekly_digest
from services.report_service import build_csv, build_excel, build_pdf
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

    taken = db.users.find_one({"watch_folder": str(resolved), "_id": {"$ne": user["id"]}})
    if taken:
        raise HTTPException(
            status_code=400, detail="Another account is already watching that folder."
        )

    db.users.update_one({"_id": user["id"]}, {"$set": {"watch_folder": str(resolved)}})
    update_watch_folder(user["id"], resolved)
    return WatchFolderOut(watch_folder=str(resolved))


@router.post("/undo", response_model=UndoResult)
def undo(db=Depends(get_db), user=Depends(get_current_user)):
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
    success, message, log = reclassify_file(log_id, request.category, db, user)
    return ReclassifyResult(success=success, message=message, log=log)


@router.post("/organize-existing", response_model=OrganizeExistingResult)
def organize_existing(db=Depends(get_db), user=Depends(get_current_user)):
    """One-time sweep of files already sitting in the watch folder root,
    e.g. everything downloaded before FileFlow started watching."""
    return organize_existing_files(db, user)


@router.post("/simulate-download", response_model=SimulateDownloadResult)
def simulate_download(user=Depends(get_current_user)):
    """Drop a small demo file into the watch folder so the live pipeline
    picks it up -- lets a demo show the real flow without waiting for an
    actual download."""
    filename = create_simulated_download(user)
    return SimulateDownloadResult(
        filename=filename, message=f"Created {filename} in the watch folder."
    )


@router.get("/reports/weekly", response_model=list[WeeklyReportStat])
def weekly_reports(weeks: int = 4, db=Depends(get_db), user=Depends(get_current_user)):
    return get_weekly_reports(db, user["id"], weeks=min(weeks, 26))


@router.post("/reports/send-digest", response_model=DigestResult)
def send_digest(db=Depends(get_db), user=Depends(get_current_user)):
    """Manually trigger the weekly email digest on demand -- lets a demo
    show it without waiting for the scheduled weekly run. Requires
    RESEND_API_KEY to be set; otherwise reports back that it was skipped."""
    if not settings.RESEND_API_KEY:
        return DigestResult(success=False, message="RESEND_API_KEY is not configured.")
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
