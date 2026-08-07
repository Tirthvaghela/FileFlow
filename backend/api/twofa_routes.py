import base64
import io
import secrets
from hashlib import sha256

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.auth import (
    create_2fa_pending_token,
    decode_2fa_pending_token,
    get_current_user,
    set_session_cookie,
    verify_password,
)
from database.db import get_db
from models.models import Document
from models.schemas import (
    TwoFactorDisableRequest,
    TwoFactorEnableOut,
    TwoFactorEnableRequest,
    TwoFactorSetupOut,
    TwoFactorStatusOut,
    TwoFactorVerifyRequest,
    UserOut,
)

router = APIRouter(prefix="/api/auth/2fa")

BACKUP_CODE_COUNT = 8
ISSUER = "FileFlow"


def _hash_backup_code(code: str) -> str:
    # Same fast, unsalted hash as password-reset tokens: these are
    # high-entropy random strings this app generates itself, never
    # user-chosen or guessable, so a slow salted hash (bcrypt) buys nothing
    # extra and would only slow down every login that uses one down.
    return sha256(code.encode("utf-8")).hexdigest()


def _generate_backup_codes() -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(BACKUP_CODE_COUNT)]


def _qr_code_data_uri(otpauth_uri: str) -> str:
    img = qrcode.make(otpauth_uri)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@router.get("/status", response_model=TwoFactorStatusOut)
def get_status(user: Document = Depends(get_current_user)):
    return TwoFactorStatusOut(enabled=bool(user.get("totp_enabled")))


@router.post("/setup", response_model=TwoFactorSetupOut)
def setup_2fa(db=Depends(get_db), user: Document = Depends(get_current_user)):
    """Generates a new secret and its QR code, but doesn't turn 2FA on yet
    -- /enable below requires proving the authenticator app actually scanned
    it correctly first, so a broken setup (wrong app, mistyped secret)
    can't lock the account out of its own login."""
    secret = pyotp.random_base32()
    db.users.update_one({"_id": user["id"]}, {"$set": {"totp_secret_pending": secret}})

    otpauth_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name=ISSUER)
    return TwoFactorSetupOut(secret=secret, qr_code_data_uri=_qr_code_data_uri(otpauth_uri))


@router.post("/enable", response_model=TwoFactorEnableOut)
def enable_2fa(
    body: TwoFactorEnableRequest, db=Depends(get_db), user: Document = Depends(get_current_user)
):
    pending_secret = user.get("totp_secret_pending")
    if not pending_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Call /setup first.")

    if not pyotp.TOTP(pending_secret).verify(body.code, valid_window=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code is incorrect or expired.")

    backup_codes = _generate_backup_codes()
    db.users.update_one(
        {"_id": user["id"]},
        {
            "$set": {
                "totp_secret": pending_secret,
                "totp_enabled": True,
                "backup_code_hashes": [_hash_backup_code(c) for c in backup_codes],
            },
            "$unset": {"totp_secret_pending": ""},
        },
    )
    return TwoFactorEnableOut(backup_codes=backup_codes)


@router.post("/disable")
def disable_2fa(
    body: TwoFactorDisableRequest, db=Depends(get_db), user: Document = Depends(get_current_user)
):
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect password.")

    db.users.update_one(
        {"_id": user["id"]},
        {
            "$set": {"totp_enabled": False},
            "$unset": {"totp_secret": "", "totp_secret_pending": "", "backup_code_hashes": ""},
        },
    )
    return {"success": True}


@router.post("/verify", response_model=UserOut)
def verify_2fa(body: TwoFactorVerifyRequest, response: Response, db=Depends(get_db)):
    """The second step of login for a 2FA-enabled account -- exchanges the
    short-lived pending_token /login issued (proof the password was
    already correct) plus a live code for the real session cookie. Not
    behind get_current_user: there's no session yet at this point, that's
    the entire reason this endpoint exists."""
    user_id = decode_2fa_pending_token(body.pending_token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This login attempt has expired -- sign in again.")

    user = db.users.find_one({"_id": user_id})
    if not user or not user.get("totp_enabled"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This login attempt has expired -- sign in again.")

    code = body.code.strip()
    if pyotp.TOTP(user["totp_secret"]).verify(code, valid_window=1):
        set_session_cookie(response, user_id)
        return Document(user)

    # Backup codes are hashed at generation time exactly as shown
    # ("ab12-cd34", dash included, see _generate_backup_codes) -- compared
    # here the same way, no normalization, so what the user sees is
    # exactly what they must type back.
    code_hash = _hash_backup_code(code)
    backup_hashes = user.get("backup_code_hashes", [])
    if code_hash in backup_hashes:
        # $pull, not overwrite-with-a-filtered-list: two logins racing on
        # the last remaining code must not both succeed by each computing
        # "remove this one" against the same stale list and re-saving it.
        db.users.update_one({"_id": user_id}, {"$pull": {"backup_code_hashes": code_hash}})
        set_session_cookie(response, user_id)
        return Document(user)

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That code is incorrect.")
