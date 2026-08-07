import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Response, status

from config.settings import settings
from database.db import get_db
from models.models import Document

COOKIE_NAME = "fileflow_session"
ALGORITHM = "HS256"
TOKEN_EXPIRY = timedelta(days=7)
# Long-lived on purpose -- this authenticates a headless background agent,
# not a browser session, so re-issuing it every 7 days like the cookie
# above would mean the agent silently stops working on a machine no one is
# actively watching. Revocation doesn't depend on this expiry: regenerating
# a token bumps the user's agent_token_version, which immediately
# invalidates every token minted with an older version (see
# get_current_agent below), so "revoke access" doesn't require waiting a
# year for the old token to expire on its own.
AGENT_TOKEN_EXPIRY = timedelta(days=365)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def hash_reset_token(token: str) -> str:
    """Password reset tokens are single-use, high-entropy random strings
    (secrets.token_urlsafe), never guessed the way a password might be --
    so unlike hash_password above, a fast unsalted hash is fine here, and
    it's what allows reset-password to look the token up with a plain
    equality query. Only the hash is ever persisted, so reading the users
    collection (a backup, a leaked snapshot) can't be replayed as a valid
    reset link -- the raw token only ever exists in the emailed link."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + TOKEN_EXPIRY,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> int | None:
    """Returns the user id encoded in a valid, unexpired *session* token, or
    None. Deliberately rejects agent tokens (see create_agent_token) even
    though both are signed with the same secret -- without this check, a
    leaked agent token (meant to run unattended on someone's own machine)
    could be pasted into a browser as a session cookie and grant full
    interactive access instead of just the narrow agent API surface."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("typ") == "agent":
            return None
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


TWOFA_PENDING_EXPIRY = timedelta(minutes=5)


def create_2fa_pending_token(user_id: int) -> str:
    """A narrow, short-lived token proving "this caller just supplied the
    right password for this account" without yet granting a real session --
    issued by /login when the account has 2FA enabled, and the only thing
    /2fa/verify below will accept in exchange for the actual session
    cookie. Never a substitute for the real session cookie itself (typ
    distinguishes it, same mechanism as the agent token's "typ": "agent")."""
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + TWOFA_PENDING_EXPIRY,
        "typ": "2fa_pending",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_2fa_pending_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("typ") != "2fa_pending":
            return None
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def create_agent_token(user_id: int, token_version: int, scope: str = "full") -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + AGENT_TOKEN_EXPIRY,
        "typ": "agent",
        "tv": token_version,
        "scope": scope,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_token(user_id),
        httponly=True,
        samesite="lax",
        secure=False,  # local http:// dev server -- flip to True behind real TLS
        max_age=int(TOKEN_EXPIRY.total_seconds()),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


def get_current_user(
    fileflow_session: str | None = Cookie(default=None),
    db=Depends(get_db),
) -> Document:
    if not fileflow_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")

    user_id = decode_token(fileflow_session)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session.")

    user = db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists.")
    return Document(user)


def get_current_agent(
    authorization: str | None = Header(default=None),
    db=Depends(get_db),
) -> Document:
    """Authenticates a remote agent process via `Authorization: Bearer
    <token>`, entirely separate from the browser's session cookie -- a
    long-running background process on someone's own machine has no
    browser to hold a cookie in, and shouldn't be forced to re-login every
    7 days the way an interactive session is."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing agent token.")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired agent token.")

    if payload.get("typ") != "agent":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an agent token.")

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid agent token.")

    user = db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists.")

    # A freshly-issued token always matches; an old one left over from
    # before the user last regenerated their token no longer does -- this
    # is what makes "regenerate" an actual revocation, not just a new
    # token that coexists with the old one forever.
    if payload.get("tv") != user.get("agent_token_version", 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Agent token has been revoked.")

    doc = Document(user)
    # From the token, not the user record -- scope is a property of this
    # specific token (chosen when it was minted), not of the account, so
    # two tokens for the same account can carry different scopes at once.
    # Missing claim means "full": tokens minted before scoping existed
    # never had this field and must keep working exactly as before.
    doc["agent_scope"] = payload.get("scope", "full")
    return doc


def require_full_agent_scope(user: Document = Depends(get_current_agent)) -> Document:
    """Gate for agent routes that actually change something (reporting
    activity, pulling and completing commands) -- a read-only token should
    be able to see an account's rules without being able to drive any of
    its automation."""
    if user["agent_scope"] != "full":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This action requires a full-control agent token."
        )
    return user
