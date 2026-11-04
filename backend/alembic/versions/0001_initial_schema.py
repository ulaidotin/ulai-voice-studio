"""initial schema

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("greeting", sa.Text(), nullable=False),
        sa.Column("closing", sa.Text(), nullable=False),
        sa.Column(
            "opening",
            sa.Enum("agent", "caller", name="opening", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("voice", sa.String(length=60), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("allow_interruptions", sa.Boolean(), nullable=False),
        sa.Column("greeting_interruptible", sa.Boolean(), nullable=False),
        sa.Column("silence_monitor", sa.Boolean(), nullable=False),
        sa.Column("backchannel_gate", sa.Boolean(), nullable=False),
        sa.Column("background_noise", sa.Boolean(), nullable=False),
        sa.Column("voicemail_detection", sa.Boolean(), nullable=False),
        sa.Column("max_call_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("engagement_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "trunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("inbound", "outbound", name="trunkdirection", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("numbers", sa.JSON(), nullable=False),
        sa.Column("allowed_addresses", sa.JSON(), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("ulai_rule_id", sa.String(length=64), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("transport", sa.String(length=8), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("ulai_trunk_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ulai_trunk_id"),
    )
    op.create_table(
        "calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("agent_name", sa.String(length=120), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("web", "outbound", "inbound", name="calldirection", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "ringing",
                "in_progress",
                "completed",
                "no_answer",
                "failed",
                name="callstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("agent_participant_id", sa.String(length=64), nullable=False),
        sa.Column("trunk_id", sa.String(length=36), nullable=True),
        sa.Column("from_number", sa.String(length=32), nullable=False),
        sa.Column("to_number", sa.String(length=32), nullable=False),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("end_reason", sa.String(length=255), nullable=False),
        sa.Column("disposition", sa.String(length=64), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("stream_seq", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trunk_id"], ["trunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    with op.batch_alter_table("calls", schema=None) as batch_op:
        batch_op.create_index("ix_calls_created_at", ["created_at"], unique=False)
        batch_op.create_index("ix_calls_status", ["status"], unique=False)

    op.create_table(
        "call_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("call_id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("transcript", "tool_call", "status", name="calleventkind", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("speaker", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("call_events", schema=None) as batch_op:
        batch_op.create_index("ix_call_events_call_seq", ["call_id", "seq"], unique=True)



def downgrade() -> None:
    with op.batch_alter_table("call_events", schema=None) as batch_op:
        batch_op.drop_index("ix_call_events_call_seq")

    op.drop_table("call_events")
    with op.batch_alter_table("calls", schema=None) as batch_op:
        batch_op.drop_index("ix_calls_status")
        batch_op.drop_index("ix_calls_created_at")

    op.drop_table("calls")
    op.drop_table("trunks")
    op.drop_table("agents")
