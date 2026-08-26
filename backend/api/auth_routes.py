import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pymongo.errors import DuplicateKeyError

from api.auth import (
    clear_session_cookie,
    create_2fa_pending_token,
    create_agent_token,
    get_current_user,
    hash_password,
    hash_reset_token,
    set_session_cookie,
    verify_password,
)
from api.rate_limit import RateLimiter, rate_limited
from config.settings import default_watch_folder_for, settings
from database.db import get_db, next_id
from models.models import Document, new_user
from models.schemas import (
    AgentTokenOut,
    AgentTokenRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResult,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UserOut,
)
from monitor.watcher import add_user_watch, remove_user_watch
from services.password_reset_service import send_password_reset_email

router = APIRouter(prefix="/api/auth")

login_limiter = RateLimiter(
    max_requests=settings.LOGIN_RATE_LIMIT_MAX,
    window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
)
register_limiter = RateLimiter(
    max_requests=settings.REGISTER_RATE_LIMIT_MAX,
    window_seconds=settings.REGISTER_RATE_LIMIT_WINDOW_SECONDS,
)
forgot_password_limiter = RateLimiter(
    max_requests=settings.PASSWORD_RESET_RATE_LIMIT_MAX,
    window_seconds=settings.PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS,
)

# Shown whether or not the email is registered -- otherwise the response
# itself would leak which emails have accounts, the same concern login's
# "invalid email or password" already guards against.
FORGOT_PASSWORD_MESSAGE = "If an account exists for that email, we've sent password reset instructions."


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
    response_model=LoginResult,
    dependencies=[Depends(rate_limited(login_limiter))],
)
def login(request: LoginRequest, response: Response, db=Depends(get_db)):
    user = db.users.find_one({"email": request.email})
    # Same error for "no such user" and "wrong password" -- don't let the
    # response leak which registered emails exist.
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")

    if user.get("totp_enabled"):
        # No session cookie yet -- the password alone isn't enough for an
        # account with 2FA on. The frontend must call /api/auth/2fa/verify
        # with this token plus a live code before a real session exists.
        return LoginResult(requires_2fa=True, pending_token=create_2fa_pending_token(user["id"]))

    set_session_cookie(response, user["id"])
    return LoginResult(user=Document(user))


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limited(forgot_password_limiter))],
)
def forgot_password(request: ForgotPasswordRequest, db=Depends(get_db)):
    user = db.users.find_one({"email": request.email})
    if user:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(
            minutes=settings.PASSWORD_RESET_TOKEN_EXPIRY_MINUTES
        )
        db.users.update_one(
            {"_id": user["id"]},
            {"$set": {"reset_token_hash": hash_reset_token(token), "reset_token_expires": expires}},
        )
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        send_password_reset_email(user["email"], reset_link)

    return MessageResponse(message=FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(request: ResetPasswordRequest, db=Depends(get_db)):
    token_hash = hash_reset_token(request.token)
    user = db.users.find_one(
        {"reset_token_hash": token_hash, "reset_token_expires": {"$gt": datetime.now(timezone.utc)}}
    )
    # Same error for "unknown token" and "expired token" -- don't give a
    # caller probing tokens any signal about which case they hit.
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired.")

    db.users.update_one(
        {"_id": user["id"]},
        {
            "$set": {"password_hash": hash_password(request.password)},
            "$unset": {"reset_token_hash": "", "reset_token_expires": ""},
        },
    )
    return MessageResponse(message="Your password has been reset. You can now sign in.")


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"success": True}


@router.get("/me", response_model=UserOut)
def me(current_user: Document = Depends(get_current_user)):
    return current_user


@router.delete("/account", response_model=MessageResponse)
def delete_account(
    request: DeleteAccountRequest,
    response: Response,
    db=Depends(get_db),
    user: Document = Depends(get_current_user),
):
    """Permanently deletes this account and everything tied to it. Requires
    the current password so a hijacked, still-logged-in session (or a
    stray click through the confirmation dialog) can't destroy an account
    on its own -- the same bar as changing a password would need."""
    if not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect password.")

    remove_user_watch(user["id"])
    db.users.delete_one({"_id": user["id"]})
    # str(), not the bare int id: RuleEngine always keys a rules document by
    # str(user_id) (see rules/rule_engine.py's get_rule_engine), never the
    # bare int -- filtering by the int here matched zero documents, so a
    # deleted account's rules silently lived on in Mongo forever. Confirmed
    # directly: the only other writer of this collection is RuleEngine
    # itself, and it never uses an int _id.
    db.rules.delete_one({"_id": str(user["id"])})
    db.activity_log.delete_many({"user_id": user["id"]})
    db.agent_commands.delete_many({"user_id": user["id"]})
    clear_session_cookie(response)
    return MessageResponse(message="Your account has been deleted.")


@router.post("/onboarding-complete", response_model=UserOut)
def complete_onboarding(db=Depends(get_db), user: Document = Depends(get_current_user)):
    db.users.update_one({"_id": user["id"]}, {"$set": {"onboarding_completed": True}})
    user["onboarding_completed"] = True
    return user


@router.post("/agent-token", response_model=AgentTokenOut)
def issue_agent_token(
    body: AgentTokenRequest | None = None,
    db=Depends(get_db),
    user: Document = Depends(get_current_user),
):
    """Mints a new long-lived token for a local agent to authenticate with,
    shown once for the user to paste into their agent's config. Bumping
    agent_token_version here is what makes this a real *regeneration* --
    any token minted before this call stops working immediately (see
    get_current_agent), rather than coexisting with the new one forever.
    That also means requesting a new "read_only" token immediately revokes
    a previously-issued "full" one (and vice versa) -- one live token per
    account at a time, same as before scoping existed.

    body is optional (defaults to a full-scope token) so every existing
    caller that posts with no body at all -- older frontend builds, the
    agent's own re-auth flow, direct API use -- keeps working unchanged."""
    scope = body.scope if body is not None else "full"
    new_version = user.get("agent_token_version", 0) + 1
    db.users.update_one({"_id": user["id"]}, {"$set": {"agent_token_version": new_version}})
    return AgentTokenOut(token=create_agent_token(user["id"], new_version, scope=scope), scope=scope)
