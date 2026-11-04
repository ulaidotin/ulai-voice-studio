from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .. import auth, schemas
from ..config import Settings, get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    # Behind the Next.js proxy the socket peer is the proxy, which appends the browser's address. Use the
    # last entry: earlier ones come from the client and could be made up to dodge the throttle.
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[-1].strip() or (request.client.host if request.client else "unknown")


@router.post("/login", response_model=schemas.Me)
async def login(
    body: schemas.LoginIn, request: Request, response: Response, settings: Settings = Depends(get_settings)
):
    key = _client_key(request)
    wait = max(auth.throttle.retry_after(key), auth.global_throttle.retry_after(auth.GLOBAL_KEY))
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed attempts. Try again in {max(1, wait // 60)} minute(s).",
            headers={"Retry-After": str(wait)},
        )
    if not auth.verify_credentials(settings, body.username, body.password):
        auth.throttle.failed(key)
        auth.global_throttle.failed(auth.GLOBAL_KEY)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    auth.throttle.succeeded(key)
    auth.issue_session(settings, response)
    return schemas.Me(username=settings.admin_username)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, settings: Settings = Depends(get_settings)):
    auth.clear_session(settings, response)


@router.get("/me", response_model=schemas.Me)
async def me(username: str = Depends(auth.require_admin)):
    return schemas.Me(username=username)
