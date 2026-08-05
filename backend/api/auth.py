from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Cookie, Depends, HTTPException, Response, status

from config.settings import settings
from database.db import get_db
from models.models import Document

COOKIE_NAME = "fileflow_session"
ALGORITHM = "HS256"
TOKEN_EXPIRY = timedelta(days=7)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + TOKEN_EXPIRY,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> int | None:
    """Returns the user id encoded in a valid, unexpired token, or None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


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
