import json
import logging
from functools import cached_property, lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


def _default_credentials_path() -> Path:
    name = Path("credentials/google-service-account.json")
    for candidate in (name, Path("..") / name):
        if candidate.exists():
            return candidate
    return name


class Settings(BaseSettings):
    # The repo-root .env, so `uvicorn` run from backend/ picks it up too; in Docker, env vars win.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    # --- App ---
    app_name: str = "Ulai Voice Studio"
    database_url: str = "postgresql+asyncpg://studio:studio@localhost:5432/studio"
    # Origin the browser uses; only needed for CORS when the frontend isn't proxying /api.
    cors_origins: list[str] = Field(default_factory=list)

    # --- The single admin account (there is no sign-up) ---
    admin_username: str = "admin"
    # bcrypt hash; generate with `python -m app.auth hash-password`.
    admin_password_hash: SecretStr = SecretStr("")
    session_secret: SecretStr = SecretStr("")
    session_ttl_hours: int = 12
    # Leave on outside local http development; the session cookie is then HTTPS-only.
    cookie_secure: bool = True

    # --- Ulai Voice Infra ---
    ulai_api_key: SecretStr = SecretStr("")
    ulai_api_url: str = "https://backend.ulai.co.in"
    ulai_cp_url: str = "https://cp.ulai.co.in"
    ulai_agent_url: str = "https://stgags.ulai.co"
    ulai_agent_api_key: SecretStr = SecretStr("")
    # Sent as X-System-Secret to the SIP originate service.
    ulai_system_secret: SecretStr = SecretStr("")
    ulai_sip_originate_url: str = "http://148.113.59.189:8082/sip/originate"

    # Browser ICE servers for web calls. TURN credentials stay server-side until a call starts.
    stun_urls: list[str] = Field(default_factory=lambda: ["stun:stun.l.google.com:19302"])
    turn_urls: list[str] = Field(default_factory=list)
    turn_username: str = ""
    turn_credential: SecretStr = SecretStr("")

    # --- AI (Gemini via Ulai's hosted agents) ---
    # Relative to the working directory: /app in Docker, the repo root or backend/ locally.
    google_credentials_path: Path = Field(default_factory=lambda: _default_credentials_path())
    gemini_location: str = "us-central1"
    ai_backend: str = "gemini-live"

    # --- Calls ---
    # Outbound calls that aren't answered within this many seconds are ended as "no answer".
    ring_timeout_seconds: int = 45

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        if self.session_secret.get_secret_value() and len(self.session_secret.get_secret_value()) < 32:
            raise ValueError("SESSION_SECRET must be at least 32 characters")
        return self

    @cached_property
    def google_credentials_json(self) -> str:
        """The service account file's contents, or "" when it isn't there."""
        try:
            raw = self.google_credentials_path.read_text(encoding="utf-8")
            json.loads(raw)
            return raw
        except FileNotFoundError:
            return ""
        except (OSError, ValueError) as err:
            log.error("Google credentials at %s are unreadable: %s", self.google_credentials_path, err)
            return ""

    @cached_property
    def gemini_project_id(self) -> str:
        if not self.google_credentials_json:
            return ""
        return json.loads(self.google_credentials_json).get("project_id", "")

    def ice_servers(self) -> list[dict]:
        servers: list[dict] = []
        if self.stun_urls:
            servers.append({"urls": self.stun_urls})
        if self.turn_urls:
            servers.append(
                {
                    "urls": self.turn_urls,
                    "username": self.turn_username,
                    "credential": self.turn_credential.get_secret_value(),
                }
            )
        return servers


@lru_cache
def get_settings() -> Settings:
    return Settings()
