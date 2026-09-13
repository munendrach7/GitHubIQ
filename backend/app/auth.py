"""Authentication, signed tokens and per-user rate limiting."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException

from .config import get_settings
from .models import RateStatus, User
from .storage import Store, get_store

PBKDF_ROUNDS = 120_000


# --------------------------------------------------------------------------- #
# Password hashing (stdlib pbkdf2 — no external dependency)
# --------------------------------------------------------------------------- #
def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    salt = salt or os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF_ROUNDS)
    return salt, dk.hex()


def verify_password(password: str, salt: str, expected: str) -> bool:
    _, computed = hash_password(password, salt)
    return hmac.compare_digest(computed, expected)


# --------------------------------------------------------------------------- #
# Signed, stateless tokens (HMAC) — no secret material is stored in the repo
# --------------------------------------------------------------------------- #
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_token(username: str, is_admin: bool) -> str:
    settings = get_settings()
    exp = int(time.time()) + settings.token_ttl_hours * 3600
    payload = _b64(json.dumps({"u": username, "a": is_admin, "e": exp}).encode())
    sig = _b64(hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_token(token: str) -> Optional[dict]:
    settings = get_settings()
    try:
        payload, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = _b64(hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
    except Exception:  # noqa: BLE001
        return None
    if data.get("e", 0) < time.time():
        return None
    return data


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
def rate_status(user: User) -> RateStatus:
    settings = get_settings()
    window = settings.rate_limit_window_hours * 3600
    max_attempts = settings.rate_limit_max_attempts
    status = RateStatus(
        window_hours=settings.rate_limit_window_hours,
        max_attempts=max_attempts,
    )
    if user.is_admin:
        status.can_generate = True
        status.used = 0
        return status

    now = time.time()
    recent = sorted(t for t in user.generations if now - t < window)
    status.used = len(recent)
    if len(recent) < max_attempts:
        status.can_generate = True
        return status
    # oldest attempt in the window must age out before the next is allowed
    oldest = recent[0]
    next_at = oldest + window
    status.can_generate = False
    status.next_allowed_at = next_at
    status.seconds_left = max(0, int(next_at - now))
    return status


def record_generation(store: Store, user: User) -> None:
    if user.is_admin:
        return
    now = time.time()
    window = get_settings().rate_limit_window_hours * 3600
    user.generations = [t for t in user.generations if now - t < window] + [now]
    store.save_user(user)


# --------------------------------------------------------------------------- #
# Current-user dependency
# --------------------------------------------------------------------------- #
def _admin_user() -> User:
    return User(id=get_settings().admin_username, username=get_settings().admin_username,
                is_admin=True)


def get_current_user(
    authorization: str = Header(default=""),
    store: Store = Depends(get_store),
) -> User:
    token = authorization[7:] if authorization.lower().startswith("bearer ") else authorization
    data = verify_token(token) if token else None
    if not data:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = data["u"]
    if data.get("a") and username == get_settings().admin_username:
        return _admin_user()
    user = store.get_user(username)
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user
