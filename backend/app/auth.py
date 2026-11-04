"""Single-admin authentication: credentials come from config, sessions are signed cookies.

Generate the password hash for ADMIN_PASSWORD_HASH with:
    python -m app.auth hash-password
"""

import getpass
import hmac
import sys
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response, status

from .config import Settings, get_settings

COOKIE = "uvs_session"
_ALGORITHM = "HS256"

# Failed logins allowed per client address within the window before it's locked out.
MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60
# Failed logins allowed from all addresses together. The per-address limit relies on X-Forwarded-For, which
# only a reverse proxy that overwrites it makes trustworthy; this cap holds even when the header is forged.
MAX_GLOBAL_FAILURES = 30
GLOBAL_KEY = "*"

# A real hash of a random password, checked when the username is wrong so both cases take the same time.
_DUMMY_HASH = bcrypt.hashpw(b"not-the-password", bcrypt.gensalt())


class LoginThrottle:
    def __init__(self, max_failures: int = MAX_FAILURES, window: float = WINDOW_SECONDS):
        self.max_failures = max_failures
        self.window = window
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again, or 0 if it isn't locked out."""
        now = time.monotonic()
        q = self._prune(key, now)
        if len(q) < self.max_failures:
            return 0
        return max(1, int(self.window - (now - q[0])))

    def failed(self, key: str) -> None:
        self._failures[key].append(time.monotonic())

    def succeeded(self, key: str) -> None:
        self._failures.pop(key, None)


throttle = LoginThrottle()
global_throttle = LoginThrottle(max_failures=MAX_GLOBAL_FAILURES)


def verify_credentials(settings: Settings, username: str, password: str) -> bool:
    stored = settings.admin_password_hash.get_secret_value().encode()
    if not stored:
        return False
    user_ok = hmac.compare_digest(username.encode(), settings.admin_username.encode())
    try:
        pw_ok = bcrypt.checkpw(password.encode(), stored if user_ok else _DUMMY_HASH)
    except ValueError:  # malformed hash in config
        return False
    return user_ok and pw_ok


def issue_session(settings: Settings, response: Response) -> None:
    now = datetime.now(UTC)
    ttl = timedelta(hours=settings.session_ttl_hours)
    token = jwt.encode(
        {"sub": settings.admin_username, "iat": now, "exp": now + ttl},
        settings.session_secret.get_secret_value(),
        algorithm=_ALGORITHM,
    )
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session(settings: Settings, response: Response) -> None:
    response.delete_cookie(COOKIE, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")


def require_admin(request: Request, settings: Settings = Depends(get_settings)) -> str:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        claims = jwt.decode(token, settings.session_secret.get_secret_value(), algorithms=[_ALGORITHM])
    except jwt.PyJWTError as err:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, sign in again") from err
    # A changed ADMIN_USERNAME invalidates existing sessions.
    if claims.get("sub") != settings.admin_username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, sign in again")
    return claims["sub"]


def _hash_password_cli() -> None:
    pw = getpass.getpass("New admin password: ")
    if len(pw) < 12:
        sys.exit("Use at least 12 characters.")
    if getpass.getpass("Repeat it: ") != pw:
        sys.exit("The passwords don't match.")
    print(bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode())


if __name__ == "__main__":
    if sys.argv[1:] != ["hash-password"]:
        sys.exit("usage: python -m app.auth hash-password")
    _hash_password_cli()
