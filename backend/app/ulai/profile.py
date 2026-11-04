import re
from datetime import UTC, datetime

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


def _tool_spec(tool: dict) -> dict:
    params = tool.get("parameters") or []
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "parameters": {
            p["name"]: {
                "type": p.get("type", "string"),
                "description": p.get("description", ""),
                "enum": p.get("enum") or [],
            }
            for p in params
        },
        "required": [p["name"] for p in params if p.get("required")],
    }


def build_profile(agent: Agent, settings: Settings, values: dict[str, str], *, direction: str) -> dict:
    return {
        "prompt": render(agent.prompt, values) or "You are a helpful voice assistant. Keep replies short.",
        "greeting": render(agent.greeting, values),
        "closing": render(agent.closing, values),
        "opening": agent.opening.value,
        "ai_backend": settings.ai_backend,
        "model": agent.model,
        "voice": agent.voice,
        "language": agent.language or None,
        "temperature": agent.temperature,
        "allow_interruptions": agent.allow_interruptions,
        "greeting_interruptible": agent.greeting_interruptible,
        "silence_monitor": agent.silence_monitor,
        "backchannel_gate": agent.backchannel_gate,
        "background_noise": agent.background_noise,
        # Voicemail detection only makes sense when we placed the call.
        "amd_enabled": agent.voicemail_detection and direction == "outbound",
        "live_transcription": True,
        "max_call_duration_seconds": agent.max_call_duration_seconds,
        "initial_engagement_deadline_ms": agent.engagement_timeout_seconds * 1000,
        "gemini_project_id": settings.gemini_project_id or None,
        "gemini_location": settings.gemini_location,
        "google_credentials_json": settings.google_credentials_json or None,
        "tools": [_tool_spec(t) for t in agent.tools or []],
    }
