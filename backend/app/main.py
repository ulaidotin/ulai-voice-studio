import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .db import dispose_engine, init_engine, sessionmaker
from .deps import Services
from .routers import agents, auth, calls, overview, trunks
from .ulai.calls import CallManager
from .ulai.gateway import Gateway, SdkGateway
from .ulai.hub import Hub
from .ulai.inbound import InboundListener

log = logging.getLogger("ulai_voice_studio")


def _check_config(settings: Settings) -> None:
    if not settings.admin_password_hash.get_secret_value():
        raise RuntimeError(
            "ADMIN_PASSWORD_HASH is not set. Generate it with: python -m app.auth hash-password"
        )
    if not settings.session_secret.get_secret_value():
        raise RuntimeError("SESSION_SECRET is not set. Use a random string of 32+ characters.")
    if not settings.google_credentials_json:
        log.warning(
            "No Google credentials at %s; agents can't start until it's added.",
            settings.google_credentials_path,
        )


def create_app(settings: Settings | None = None, gateway: Gateway | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _check_config(settings)
        init_engine(settings.database_url)
        gw = gateway or SdkGateway(settings)
        hub = Hub()
        call_manager = CallManager(gw, settings, sessionmaker(), hub)
        inbound = InboundListener(gw, sessionmaker(), call_manager)
        app.state.services = Services(gateway=gw, hub=hub, calls=call_manager, inbound=inbound)
        await call_manager.resume()
        inbound.start()
        try:
            yield
        finally:
            await inbound.stop()
            await call_manager.shutdown()
            await gw.close()
            await dispose_engine()

    app = FastAPI(
        title=settings.app_name, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    for r in (auth.router, agents.router, trunks.router, calls.router, overview.router):
        app.include_router(r)

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"ok": True}

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
