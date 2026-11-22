"""Simple password/PIN authentication with HMAC-signed cookies for Web UI."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

from fastapi import HTTPException, Request, Response, status

from app.config import PUBLIC_URL, SECRET_KEY, SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS, WEB_PASSWORD


def is_auth_enabled() -> bool:
    return bool(WEB_PASSWORD)


def _sign(payload: str) -> str:
    return hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token() -> str:
    exp = int(time.time()) + SESSION_MAX_AGE_SECONDS
    payload = f"auth:{exp}"
    sig = _sign(payload)
    return f"{payload}:{sig}"


def verify_session_token(token: Optional[str]) -> bool:
    if not is_auth_enabled():
        return True
    if not token:
        return False
    parts = token.split(":")
    if len(parts) != 3 or parts[0] != "auth":
        return False
    payload = f"{parts[0]}:{parts[1]}"
    expected = _sign(payload)
    if not hmac.compare_digest(parts[2], expected):
        return False
    try:
        exp = int(parts[1])
    except ValueError:
        return False
    return time.time() < exp


def verify_password(password: str) -> bool:
    if not is_auth_enabled():
        return True
    return hmac.compare_digest(password.strip(), WEB_PASSWORD)


def set_session_cookie(response: Response) -> None:
    token = create_session_token()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=PUBLIC_URL.startswith("https://"),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME)


def require_auth(request: Request) -> None:
    """FastAPI dependency that enforces Web UI authentication when WEB_PASSWORD is set."""
    if not is_auth_enabled():
        return
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if verify_session_token(cookie_token):
        return
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and verify_session_token(auth_header[7:].strip()):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Tizimga kirish talab qilinadi (parol/PIN noto'g'ri yoki muddati tugagan).",
    )
