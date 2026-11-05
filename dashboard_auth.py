"""Local browser authentication, separate from API service credentials."""
from dataclasses import dataclass
import hashlib
import os
import secrets
from threading import Lock
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response

router = APIRouter(prefix="/dashboard")
COOKIE = "aegisops_dashboard"
TTL = 3600
lock = Lock()
sessions = {}
attempts = {}


@dataclass
class Session:
    csrf: str
    expires: float


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${digest}"


def check_origin(request: Request):
    origin = os.getenv("DASHBOARD_ORIGIN", "http://127.0.0.1:8001")
    parsed = urlsplit(origin)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1", "testserver"}:
        raise HTTPException(503, "Dashboard origin is not configured for local use")
    if request.headers.get("origin") != origin or request.headers.get("host") != parsed.netloc:
        raise HTTPException(403, "Same-origin request required")


def browser_session(request: Request):
    origin = urlsplit(os.getenv("DASHBOARD_ORIGIN", "http://127.0.0.1:8001"))
    if request.headers.get("host") != origin.netloc:
        raise HTTPException(403, "Dashboard host is not allowed")
    if request.headers.get("sec-fetch-site") not in {None, "same-origin", "none"}:
        raise HTTPException(403, "Same-origin request required")
    now = time.monotonic()
    with lock:
        for key in [key for key, value in sessions.items() if value.expires <= now]:
            sessions.pop(key, None)
        session = sessions.get(request.cookies.get(COOKIE, ""))
    if session is None:
        raise HTTPException(401, "Dashboard login required")
    return session


@router.post("/login")
async def login(request: Request, response: Response):
    check_origin(request)
    stored = os.getenv("DASHBOARD_PASSWORD_HASH", "")
    if not stored:
        raise HTTPException(503, "Dashboard login is not configured")
    # Bound parsing; never let validation responses echo a password.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(413, "Login request is too large")
    import json
    try:
        data = json.loads(body)
        password = data.get("password") if isinstance(data, dict) else None
        if not isinstance(password, str) or not 1 <= len(password) <= 512:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, "A dashboard password is required") from None
    now = time.monotonic()
    address = request.client.host if request.client else "local"
    with lock:
        for key in [key for key, value in attempts.items() if value[1] <= now]:
            attempts.pop(key, None)
        count, until = attempts.get(address, (0, now + 300))
        if count >= 5:
            raise HTTPException(429, "Too many login attempts. Try again in five minutes")
        attempts[address] = (count + 1, until)
    try:
        kind, salt, digest = stored.split("$")
        valid = kind == "scrypt" and secrets.compare_digest(password_hash(password, salt), stored)
    except (ValueError, TypeError):
        raise HTTPException(503, "Dashboard login is not configured") from None
    if not valid:
        raise HTTPException(401, "Invalid dashboard password")
    token = secrets.token_urlsafe(32)
    session = Session(secrets.token_urlsafe(32), now + TTL)
    with lock:
        attempts.pop(address, None)
        sessions.pop(request.cookies.get(COOKIE, ""), None)
        if len(sessions) >= 100:
            sessions.pop(next(iter(sessions)))
        sessions[token] = session
    response.set_cookie(COOKIE, token, max_age=TTL, httponly=True, samesite="strict",
                        secure=os.getenv("DASHBOARD_COOKIE_SECURE") == "1", path="/dashboard")
    return {"csrf_token": session.csrf, "expires_in": TTL}


@router.get("/session")
def session_info(session=Depends(browser_session)):
    return {"csrf_token": session.csrf, "expires_in": max(0, int(session.expires - time.monotonic()))}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session=Depends(browser_session)):
    check_origin(request)
    if not secrets.compare_digest(request.headers.get("x-csrf-token", "").encode(), session.csrf.encode()):
        raise HTTPException(403, "Invalid CSRF token")
    with lock:
        sessions.pop(request.cookies.get(COOKIE, ""), None)
    response.delete_cookie(COOKIE, path="/dashboard")
