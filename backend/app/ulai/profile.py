import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import ulai_agents as ua

from ..config import Settings
from ..models import Agent

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def call_variables(agent: Agent, given: dict[str, str], builtins: dict[str, str]) -> dict[str, str]:
    """The values {{placeholders}} resolve to: agent defaults, then built-ins, then per-call values."""
    values = {v["name"]: v.get("default", "") for v in agent.variables or []}
    values.update({k: v for k, v in builtins.items() if v})
    values.update(given)
    return values


def render(text: str, values: dict[str, str]) -> str:
    # Unknown placeholders render empty rather than reaching the caller as "{{name}}".
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), ""), text or "")


# Filled in by the studio on every call; shown in the editor's {{variable}} picker.
BUILTIN_VARIABLES = [
    {"name": "caller_number", "description": "The other party's phone number (empty for web calls)"},
    {"name": "call_direction", "description": "web, inbound or outbound"},
    {"name": "current_date", "description": "Today's date, e.g. Monday, 03 November 2026"},
    {"name": "current_time_utc", "description": "The time the call started, in UTC"},
]


def builtins(*, direction: str, from_number: str = "", to_number: str = "") -> dict[str, str]:
    now = datetime.now(UTC)
    caller = to_number if direction == "outbound" else from_number
    return {
        "call_direction": direction,
        "caller_number": caller,
        "current_date": now.strftime("%A, %d %B %Y"),
        "current_time_utc": now.strftime("%H:%M UTC"),
    }


# Answers one of an agent's tools for one call: (the tool's config, the model's arguments) -> result.
ToolAnswer = Callable[[dict, dict[str, Any]], Awaitable[dict]]


def build_tools(tools: list[dict], answer: ToolAnswer | None = None) -> list[ua.Tool]:
    """The agent's tools for ulai_agents. With `answer`, each is answered by this process."""

    def handler(tool: dict) -> Callable[[dict[str, Any]], Awaitable[dict]]:
        async def handle(args: dict[str, Any]) -> dict:
            return await answer(tool, args)

        return handle

    out = []
    for t in tools or []:
        params = t.get("parameters") or []
        out.append(
            ua.tool_from_schema(
                t["name"],
                t.get("description", ""),
                {
                    p["name"]: ua.Param(
                        type=p.get("type", "string"),
                        description=p.get("description", ""),
                        enum=p.get("enum") or None,
                    )
                    for p in params
                },
                [p["name"] for p in params if p.get("required")],
                handler(t) if answer else None,
            )
        )
    return out


def build_agent(agent: Agent, settings: Settings, values: dict[str, str], *, direction: str) -> ua.Agent:
    """The agent as ulai_agents sends it: Ulai keeps no agents, so it travels with every call."""
    cloud = None
    if settings.google_credentials_json:
        cloud = ua.CloudAccount(
            project=settings.gemini_project_id,
            region=settings.gemini_location,
            credentials_json=settings.google_credentials_json,
        )
    return ua.Agent(
        id=agent.id,
        instructions=render(agent.prompt, values) or "You are a helpful voice assistant. Keep replies short.",
        greeting=render(agent.greeting, values),
        closing=render(agent.closing, values),
        opening=agent.opening.value,
        voice=agent.voice,
        language=agent.language or None,
        pipeline=ua.Realtime(model=agent.model),
        temperature=agent.temperature,
        max_duration=timedelta(seconds=agent.max_call_duration_seconds or 0) or None,
        cloud=cloud,
        tools=build_tools(agent.tools),
        options=ua.Options(
            interruptible=agent.allow_interruptions,
            greeting_interruptible=agent.greeting_interruptible,
            silence_monitor=agent.silence_monitor,
            backchannel_gate=agent.backchannel_gate,
            background_noise=agent.background_noise,
            # Voicemail detection only makes sense when we placed the call.
            voicemail_detection=agent.voicemail_detection and direction == "outbound",
            live_transcription=True,
            first_words_timeout=timedelta(seconds=agent.engagement_timeout_seconds),
        ),
    )
