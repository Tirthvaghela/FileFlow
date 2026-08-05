from fastapi import APIRouter, Depends, HTTPException, Response, status
from pymongo.errors import DuplicateKeyError

from api.auth import (
    clear_session_cookie,
    get_current_user,
    hash_password,
    set_session_cookie,
    verify_password,
)
from api.rate_limit import RateLimiter, rate_limited
from config.settings import default_watch_folder_for, settings
from database.db import get_db, next_id
from models.models import Document, new_user
from models.schemas import LoginRequest, RegisterRequest, UserOut
from monitor.watcher import add_user_watch

router = APIRouter(prefix="/api/auth")

login_limiter = RateLimiter(
    max_requests=settings.LOGIN_RATE_LIMIT_MAX,
    window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
)
register_limiter = RateLimiter(
    max_requests=settings.REGISTER_RATE_LIMIT_MAX,
    window_seconds=settings.REGISTER_RATE_LIMIT_WINDOW_SECONDS,
)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limited(register_limiter))],
)
def register(request: RegisterRequest, response: Response, db=Depends(get_db)):
    existing = db.users.find_one({"email": request.email})
    if existing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "An account with this email already exists."
        )

    # The id has to exist before the default watch folder path can be
    # computed (user_<id>), so it's reserved up front rather than going
    # through insert_with_id.
    user_id = next_id(db, "users")
    watch_folder = default_watch_folder_for(user_id)
    doc = new_user(
        email=request.email,
        password_hash=hash_password(request.password),
        watch_folder=str(watch_folder),
    )
    doc["_id"] = user_id
    doc["id"] = user_id
    try:
        db.users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "An account with this email already exists."
        )

    add_user_watch(user_id, watch_folder)
    set_session_cookie(response, user_id)
    return Document(doc)


@router.post(
    "/login",
    response_model=UserOut,
    dependencies=[Depends(rate_limited(login_limiter))],
)
def login(request: LoginRequest, response: Response, db=Depends(get_db)):
    user = db.users.find_one({"email": request.email})
    # Same error for "no such user" and "wrong password" -- don't let the
    # response leak which registered emails exist.
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")

    set_session_cookie(response, user["id"])
    return Document(user)


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"success": True}


@router.get("/me", response_model=UserOut)
def me(current_user: Document = Depends(get_current_user)):
    return current_user
