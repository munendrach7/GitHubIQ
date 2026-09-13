"""Authentication routes: signup, login, and current-user status."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException

from ..auth import (
    get_current_user,
    hash_password,
    issue_token,
    rate_status,
    verify_password,
)
from ..config import get_settings
from ..models import AuthResponse, Credentials, RateStatus, User
from ..storage import Store, get_store

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _is_admin_login(creds: Credentials) -> bool:
    import hashlib

    settings = get_settings()
    if creds.username.lower() != settings.admin_username.lower():
        return False
    return hashlib.sha256(creds.password.encode()).hexdigest() == settings.admin_password_hash


@router.post("/signup", response_model=AuthResponse)
def signup(creds: Credentials, store: Store = Depends(get_store)) -> AuthResponse:
    settings = get_settings()
    if creds.username.lower() == settings.admin_username.lower():
        raise HTTPException(status_code=400, detail="This username is reserved")
    if store.get_user(creds.username):
        raise HTTPException(status_code=409, detail="Username already exists")
    salt, pwd_hash = hash_password(creds.password)
    user = User(
        id=creds.username.lower(),
        username=creds.username,
        salt=salt,
        password_hash=pwd_hash,
        created_at=time.time(),
    )
    store.save_user(user)
    return AuthResponse(
        token=issue_token(user.username, False),
        username=user.username,
        is_admin=False,
        rate=rate_status(user),
    )


@router.post("/login", response_model=AuthResponse)
def login(creds: Credentials, store: Store = Depends(get_store)) -> AuthResponse:
    if _is_admin_login(creds):
        admin = User(id=get_settings().admin_username, username=get_settings().admin_username,
                     is_admin=True)
        return AuthResponse(
            token=issue_token(admin.username, True),
            username=admin.username,
            is_admin=True,
            rate=rate_status(admin),
        )

    user = store.get_user(creds.username)
    if user is None or not verify_password(creds.password, user.salt, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return AuthResponse(
        token=issue_token(user.username, False),
        username=user.username,
        is_admin=False,
        rate=rate_status(user),
    )


@router.get("/me", response_model=AuthResponse)
def me(user: User = Depends(get_current_user)) -> AuthResponse:
    # token is re-issued so the client always holds a fresh one
    return AuthResponse(
        token=issue_token(user.username, user.is_admin),
        username=user.username,
        is_admin=user.is_admin,
        rate=rate_status(user),
    )


@router.get("/rate", response_model=RateStatus)
def rate(user: User = Depends(get_current_user)) -> RateStatus:
    return rate_status(user)
