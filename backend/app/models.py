import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Timestamps always come back timezone-aware in UTC, whatever the database driver returns."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


def _enum(cls: type[enum.Enum]) -> Enum:
    # Stored as plain strings so adding a value never needs a database enum migration.
    return Enum(cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


class Opening(enum.StrEnum):
    AGENT = "agent"
    CALLER = "caller"


class TrunkDirection(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallDirection(enum.StrEnum):
    WEB = "web"
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class CallStatus(enum.StrEnum):
    QUEUED = "queued"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    FAILED = "failed"

    @property
    def is_final(self) -> bool:
        return self in (CallStatus.COMPLETED, CallStatus.NO_ANSWER, CallStatus.FAILED)


ACTIVE_CALL_STATUSES = (CallStatus.QUEUED, CallStatus.RINGING, CallStatus.IN_PROGRESS)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")

    # Behaviour
    prompt: Mapped[str] = mapped_column(Text, default="")
    greeting: Mapped[str] = mapped_column(Text, default="")
    closing: Mapped[str] = mapped_column(Text, default="")
    opening: Mapped[Opening] = mapped_column(_enum(Opening), default=Opening.AGENT)

    # Voice & model
    model: Mapped[str] = mapped_column(String(120))
    voice: Mapped[str] = mapped_column(String(60))
    language: Mapped[str] = mapped_column(String(20), default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.7)

    # Conversation
    allow_interruptions: Mapped[bool] = mapped_column(default=True)
    greeting_interruptible: Mapped[bool] = mapped_column(default=True)
    silence_monitor: Mapped[bool] = mapped_column(default=True)
    backchannel_gate: Mapped[bool] = mapped_column(default=True)
    background_noise: Mapped[bool] = mapped_column(default=False)
    voicemail_detection: Mapped[bool] = mapped_column(default=False)
    max_call_duration_seconds: Mapped[int] = mapped_column(Integer, default=900)
    engagement_timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)

    # [{name, default, description}]
    variables: Mapped[list] = mapped_column(JSON, default=list)
    # [{name, description, url, method, headers, parameters: [{name, type, description, required, enum}],
    #   timeout_seconds}]
    tools: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Trunk(Base):
    __tablename__ = "trunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(120))
    direction: Mapped[TrunkDirection] = mapped_column(_enum(TrunkDirection))
    enabled: Mapped[bool] = mapped_column(default=True)
    # Inbound: the numbers that ring this trunk. Outbound: the caller IDs calls can be placed from.
    numbers: Mapped[list] = mapped_column(JSON, default=list)

    # Inbound only
    allowed_addresses: Mapped[list] = mapped_column(JSON, default=list)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    ulai_rule_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Outbound only. The password is stored by Ulai, never here.
    address: Mapped[str] = mapped_column(String(255), default="")
    transport: Mapped[str] = mapped_column(String(8), default="auto")
    username: Mapped[str] = mapped_column(String(255), default="")

    ulai_trunk_id: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    agent: Mapped[Agent | None] = relationship(lazy="joined")


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (Index("ix_calls_created_at", "created_at"), Index("ix_calls_status", "status"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    # Kept so history still reads well after the agent is renamed or deleted.
    agent_name: Mapped[str] = mapped_column(String(120), default="")
    direction: Mapped[CallDirection] = mapped_column(_enum(CallDirection))
    status: Mapped[CallStatus] = mapped_column(_enum(CallStatus), default=CallStatus.QUEUED)

    session_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    agent_participant_id: Mapped[str] = mapped_column(String(64), default="")
    trunk_id: Mapped[str | None] = mapped_column(ForeignKey("trunks.id", ondelete="SET NULL"), nullable=True)
    from_number: Mapped[str] = mapped_column(String(32), default="")
    to_number: Mapped[str] = mapped_column(String(32), default="")
    variables: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_reason: Mapped[str] = mapped_column(String(255), default="")
    disposition: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    # {prompt_tokens, response_tokens, cached_tokens}
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    # Last agent-stream event stored, so re-attaching (which replays history) doesn't duplicate lines.
    stream_seq: Mapped[int] = mapped_column(Integer, default=0)

    events: Mapped[list["CallEvent"]] = relationship(
        back_populates="call", order_by="CallEvent.seq", cascade="all, delete-orphan"
    )


class CallEventKind(enum.StrEnum):
    TRANSCRIPT = "transcript"
    TOOL_CALL = "tool_call"
    STATUS = "status"


class CallEvent(Base):
    """One line of a call's timeline: something said, a tool used, or a status change."""

    __tablename__ = "call_events"
    __table_args__ = (Index("ix_call_events_call_seq", "call_id", "seq", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[CallEventKind] = mapped_column(_enum(CallEventKind))
    # "agent" | "caller" for transcript lines
    speaker: Mapped[str] = mapped_column(String(16), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    call: Mapped[Call] = relationship(back_populates="events")
