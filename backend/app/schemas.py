import re
from datetime import datetime
from typing import Annotated, Literal

import phonenumbers
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl, field_validator

from . import catalog
from .models import CallDirection, CallEventKind, CallStatus, Opening, TrunkDirection

IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")


def e164(value: str) -> str:
    """Normalises a phone number to E.164; it must include the country code."""
    try:
        parsed = phonenumbers.parse(value, None)
    except phonenumbers.NumberParseException as err:
        raise ValueError("Enter the number with its country code, e.g. +14155550123") from err
    if not phonenumbers.is_possible_number(parsed):
        raise ValueError(f"{value} is not a valid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


PhoneNumber = Annotated[str, AfterValidator(e164)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------


class LoginIn(BaseModel):
    username: str = Field(max_length=120)
    password: str = Field(max_length=256)


class Me(BaseModel):
    username: str


# ---------- Agents ----------


class Variable(BaseModel):
    name: str
    default: str = ""
    description: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not IDENT.match(v):
            raise ValueError("Variable names use letters, numbers and _, and can't start with a number")
        return v


class ToolParameter(BaseModel):
    name: str
    type: Literal["string", "number", "integer", "boolean"] = "string"
    description: str = ""
    required: bool = False
    enum: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not IDENT.match(v):
            raise ValueError("Parameter names use letters, numbers and _")
        return v


class Tool(BaseModel):
    """A function the agent can call mid-conversation; the studio answers it by calling `url`."""

    name: str
    description: str = Field(min_length=1, max_length=1000)
    url: HttpUrl
    method: Literal["GET", "POST"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    parameters: list[ToolParameter] = Field(default_factory=list)
    timeout_seconds: int = Field(default=10, ge=1, le=30)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not IDENT.match(v):
            raise ValueError("Tool names use letters, numbers and _, e.g. check_order_status")
        return v


class AgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)

    prompt: str = Field(default="", max_length=50_000)
    greeting: str = Field(default="", max_length=2000)
    closing: str = Field(default="", max_length=2000)
    opening: Opening = Opening.AGENT

    model: str = catalog.DEFAULT_MODEL
    voice: str = catalog.DEFAULT_VOICE
    language: str = ""
    temperature: float = Field(default=0.7, ge=0, le=2)

    allow_interruptions: bool = True
    greeting_interruptible: bool = True
    silence_monitor: bool = True
    backchannel_gate: bool = True
    background_noise: bool = False
    voicemail_detection: bool = False
    max_call_duration_seconds: int = Field(default=900, ge=30, le=7200)
    engagement_timeout_seconds: int = Field(default=30, ge=5, le=300)

    variables: list[Variable] = Field(default_factory=list)
    tools: list[Tool] = Field(default_factory=list)

    @field_validator("model")
    @classmethod
    def _model(cls, v: str) -> str:
        if v not in catalog.MODEL_IDS:
            raise ValueError(f"Unknown model {v}")
        return v

    @field_validator("voice")
    @classmethod
    def _voice(cls, v: str) -> str:
        if v not in catalog.VOICE_IDS:
            raise ValueError(f"Unknown voice {v}")
        return v

    @field_validator("language")
    @classmethod
    def _language(cls, v: str) -> str:
        if v not in catalog.LANGUAGE_IDS:
            raise ValueError(f"Unsupported language {v}")
        return v

    @field_validator("variables")
    @classmethod
    def _unique_variables(cls, v: list[Variable]) -> list[Variable]:
        names = [x.name for x in v]
        if len(names) != len(set(names)):
            raise ValueError("Variable names must be unique")
        return v

    @field_validator("tools")
    @classmethod
    def _unique_tools(cls, v: list[Tool]) -> list[Tool]:
        names = [x.name for x in v]
        if len(names) != len(set(names)):
            raise ValueError("Tool names must be unique")
        return v


class AgentIn(AgentBase):
    pass


class AgentOut(AgentBase, ORM):
    id: str
    created_at: datetime
    updated_at: datetime


class AgentSummary(ORM):
    id: str
    name: str
    description: str
    voice: str
    language: str
    opening: Opening
    updated_at: datetime
    calls_total: int = 0
    calls_last_7d: int = 0
    inbound_numbers: list[str] = Field(default_factory=list)


# ---------- Trunks ----------


class InboundTrunkIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    numbers: list[PhoneNumber] = Field(min_length=1)
    allowed_addresses: list[str] = Field(default_factory=list)
    agent_id: str | None = None


class InboundTrunkUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    numbers: list[PhoneNumber] | None = Field(default=None, min_length=1)
    allowed_addresses: list[str] | None = None
    # Present and null unassigns the agent; absent leaves it unchanged.
    agent_id: str | None = None


class OutboundTrunkIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=3, max_length=255)
    transport: Literal["auto", "udp", "tcp", "tls"] = "auto"
    username: str = Field(default="", max_length=255)
    password: str = Field(default="", max_length=255)
    numbers: list[PhoneNumber] = Field(min_length=1)


class OutboundTrunkUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, min_length=3, max_length=255)
    transport: Literal["auto", "udp", "tcp", "tls"] | None = None
    username: str | None = Field(default=None, max_length=255)
    # Only sent when changing it.
    password: str | None = Field(default=None, max_length=255)
    numbers: list[PhoneNumber] | None = Field(default=None, min_length=1)


class TrunkAgent(ORM):
    id: str
    name: str


class TrunkOut(ORM):
    id: str
    name: str
    direction: TrunkDirection
    enabled: bool
    numbers: list[str]
    allowed_addresses: list[str]
    agent: TrunkAgent | None
    address: str
    transport: str
    username: str
    created_at: datetime
    updated_at: datetime


class EnabledIn(BaseModel):
    enabled: bool


# ---------- Calls ----------


class WebCallIn(BaseModel):
    agent_id: str
    variables: dict[str, str] = Field(default_factory=dict)
    # Unsaved edits to try out; the call runs on these instead of the saved agent.
    draft: AgentIn | None = None


class WebCallOut(BaseModel):
    call_id: str
    session_id: str
    participant_id: str
    ticket: str
    node_address: str
    events_token: str | None
    control_plane_url: str
    ice_servers: list[dict]


class OutboundCallIn(BaseModel):
    agent_id: str
    trunk_id: str
    to_number: PhoneNumber
    from_number: PhoneNumber | None = None
    variables: dict[str, str] = Field(default_factory=dict)


class CallEventOut(ORM):
    seq: int
    kind: CallEventKind
    speaker: str
    text: str
    data: dict
    elapsed_ms: int | None
    created_at: datetime


class CallOut(ORM):
    id: str
    agent_id: str | None
    agent_name: str
    direction: CallDirection
    status: CallStatus
    trunk_id: str | None
    from_number: str
    to_number: str
    variables: dict
    created_at: datetime
    answered_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    end_reason: str
    disposition: str
    error: str
    usage: dict


class CallDetail(CallOut):
    events: list[CallEventOut]


class CallPage(BaseModel):
    items: list[CallOut]
    total: int
    page: int
    page_size: int


# ---------- Overview ----------


class DailyCount(BaseModel):
    date: str
    web: int
    inbound: int
    outbound: int


class Overview(BaseModel):
    active_calls: int
    calls_today: int
    calls_7d: int
    answer_rate_7d: float | None
    avg_duration_7d: float | None
    total_minutes_7d: float
    daily: list[DailyCount]
    recent: list[CallOut]
    agents: int
    trunks: int


class CatalogModel(BaseModel):
    id: str
    name: str
    description: str


class CatalogVoice(BaseModel):
    id: str
    style: str


class CatalogLanguage(BaseModel):
    id: str
    name: str


class BuiltinVariable(BaseModel):
    name: str
    description: str


class Catalog(BaseModel):
    models: list[CatalogModel]
    voices: list[CatalogVoice]
    languages: list[CatalogLanguage]
    builtin_variables: list[BuiltinVariable]


class HealthOut(BaseModel):
    ulai: Literal["ok", "unconfigured", "error"]
    ulai_detail: str = ""
    project_id: str | None = None
    google_credentials: bool
    inbound_listener: Literal["running", "idle", "error"]
