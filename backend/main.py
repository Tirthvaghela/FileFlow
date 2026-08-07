import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.agent_routes import router as agent_router
from api.auth_routes import router as auth_router
from api.routes import router as api_router
from api.twofa_routes import router as twofa_router
from api.websocket_manager import manager
from api.ws import router as ws_router
from config.settings import settings
from database.db import init_db
from monitor.watcher import start_watcher
from scheduler.archive_scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.FileHandler(settings.LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger("fileflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    import asyncio

    loop = asyncio.get_running_loop()
    observer = start_watcher(loop, manager.broadcast)
    scheduler = start_scheduler()

    logger.info("FileFlow backend started.")
    yield

    observer.stop()
    observer.join(timeout=5)
    scheduler.shutdown(wait=False)
    logger.info("FileFlow backend stopped.")


app = FastAPI(title="FileFlow API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(twofa_router)
app.include_router(api_router)
app.include_router(agent_router)
app.include_router(ws_router)


@app.get("/")
def root():
    return {"name": "FileFlow API", "status": "running"}


@app.get("/api/health")
def health():
    # Deliberately unauthenticated -- the frontend needs to reach this
    # before a session exists. Each account has its own watch folder now
    # (see UserOut.watch_folder / GET /api/auth/me), so there's no single
    # global folder left to report here.
    return {"status": "ok"}
