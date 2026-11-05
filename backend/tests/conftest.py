import asyncio
import json
from collections import defaultdict
from datetime import timedelta
from typing import Any

import bcrypt
import httpx
import pytest
import ulai_agents as ua
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings, get_settings
from app.db import Base
from app.main import create_app
from app.ulai.gateway import RemoteRule, RemoteTrunk, UlaiError, UserJoin

PASSWORD = "correct horse battery staple"


class FakeSession:
    """An attached call, as ulai-agents gives it: events in order, tools answered in the background."""

    def __init__(self, gw: "FakeGateway", session_id: str, tools: list[ua.Tool]):
        self.gw = gw
        self.session_id = session_id
        self.tools = {t.name: t for t in tools}
        self.answers: list[tuple[str, Any]] = []
        self.closed = False

    async def events(self):
        q = self.gw.agent_queues[self.session_id]
        while True:
            ev = await q.get()
            if ev is None:  # the stream drops
                return
            if isinstance(ev, Exception):
                raise ev
            tool = self.tools.get(ev.name) if isinstance(ev, ua.ToolCall) else None
            if tool is not None and tool.handler is not None:
                asyncio.ensure_future(self._answer(tool, ev.args))
            yield ev

    async def _answer(self, tool: ua.Tool, args: dict) -> None:
        self.answers.append((tool.name, await tool.handler(args)))

    async def close(self) -> None:
        self.closed = True


class FakeGateway:
    """Stands in for Ulai. Tests push agent/control-plane events through the queues."""

    def __init__(self) -> None:
        self.project_id = "proj-test"
        self.log: list[tuple] = []
        self.fail: set[str] = set()
        self.agent_queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.session_queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.sessions: list[FakeSession] = []
        self.project_queue: asyncio.Queue = asyncio.Queue()
        self.subscribed: list[str | None] = []
        self._n = 0

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n}"

    def _record(self, name: str, *args: Any) -> None:
        if name in self.fail:
            raise UlaiError(f"{name} failed")
        self.log.append((name, *args))

    def calls(self, name: str) -> list[tuple]:
        return [entry for entry in self.log if entry[0] == name]

    async def check(self) -> str:
        return self.project_id

    async def close(self) -> None:
        pass

    async def create_session(self, metadata):
        self._record("create_session", metadata)
        return self._id("sess")

    async def join_user(self, session_id, participant_id):
        self._record("join_user", session_id, participant_id)
        return UserJoin(session_id, f"conn-{participant_id}", "ticket-1", "node.example:443", "events-1")

    async def join_agent(self, session_id, agent, participant_id, fields):
        agent.validate(allow_unlisted_values=True)  # as ulai-agents does before sending it
        self._record("join_agent", session_id, agent, participant_id, fields)

    async def leave_agent(self, session_id, participant_id, reason):
        self._record("leave_agent", session_id, participant_id, reason)

    async def terminate_session(self, session_id):
        self._record("terminate_session", session_id)

    async def watch_session(self, session_id):
        return "watch-token"

    async def session_events(self, session_id, last_event_id):
        q = self.session_queues[session_id]
        while True:
            msg = await q.get()
            if msg is None:
                return
            yield msg

    async def project_events(self, last_event_id):
        self.subscribed.append(last_event_id)
        while True:
            yield await self.project_queue.get()

    async def originate(self, *, session_id, trunk_id, to_number, from_number):
        self._record("originate", session_id, trunk_id, to_number, from_number)

    async def attach(self, session_id, tools):
        self._record("attach", session_id, [t.name for t in tools])
        session = FakeSession(self, session_id, tools)
        self.sessions.append(session)
        return session

    async def create_inbound_trunk(self, name, numbers, allowed):
        self._record("create_inbound_trunk", name, numbers, allowed)
        return RemoteTrunk(self._id("in"))

    async def update_inbound_trunk(self, trunk_id, name, numbers, allowed):
        self._record("update_inbound_trunk", trunk_id, name, numbers, allowed)

    async def create_outbound_trunk(self, name, address, transport, username, password):
        self._record("create_outbound_trunk", name, address, transport, username, password)
        return RemoteTrunk(self._id("out"))

    async def update_outbound_trunk(self, trunk_id, **fields):
        self._record("update_outbound_trunk", trunk_id, fields)

    async def set_trunk_enabled(self, direction, trunk_id, enabled):
        self._record("set_trunk_enabled", direction, trunk_id, enabled)

    async def delete_trunk(self, direction, trunk_id):
        self._record("delete_trunk", direction, trunk_id)

    async def create_rule(self, name, agent_id, trunk_id):
        self._record("create_rule", name, agent_id, trunk_id)
        return RemoteRule(self._id("rule"))

    async def update_rule(self, rule_id, agent_id):
        self._record("update_rule", rule_id, agent_id)

    async def delete_rule(self, rule_id):
        self._record("delete_rule", rule_id)


# ---- ulai_agents event builders ----


def said(speaker, text, final=True, elapsed_ms=0):
    return ua.Transcript(
        speaker=ua.Speaker(speaker), text=text, final=final, elapsed=timedelta(milliseconds=elapsed_ms)
    )


def tool_call(name, args, call_id="tc-1"):
    return ua.ToolCall(id=call_id, name=name, args=args, args_json=json.dumps(args))


def usage(prompt, response):
    return ua.Usage(prompt_total=prompt, response_total=response)


def ended(reason="caller hung up", disposition="completed"):
    return ua.Ended(reason=reason, disposition=disposition)


def caller_arrived(session_id, agent_id, from_number, to_number, direction="INBOUND", event_id="e1"):
    """The control plane announcing a phone caller joining a session, as the SIP gateway joins it."""
    return {
        "id": event_id,
        "type": "participant_joined",
        "session_id": session_id,
        "kind": "SIP",
        "sip_direction": direction,
        "metadata": {
            "assigned_agent": agent_id,
            "caller_id": from_number,
            "phone_number": to_number,
            "direction": direction.lower(),
            "role": "telephony",
        },
    }


async def eventually(check, within=3.0):
    """Polls an async predicate until it holds; background call monitors finish asynchronously."""
    deadline = asyncio.get_running_loop().time() + within
    while True:
        result = await check()
        if result:
            return result
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


@pytest.fixture
def settings(tmp_path) -> Settings:
    creds = tmp_path / "google.json"
    creds.write_text(json.dumps({"type": "service_account", "project_id": "gcp-proj"}))
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        admin_username="admin",
        admin_password_hash=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode(),
        session_secret="x" * 40,
        cookie_secure=False,
        ulai_api_key="ulai_test",
        google_credentials_path=creds,
        ring_timeout_seconds=30,
    )


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
async def app(settings, gateway):
    from app import auth

    auth.throttle._failures.clear()
    auth.global_throttle._failures.clear()
    # Tables exist before startup, as they do in production where migrations run first.
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    application = create_app(settings, gateway)
    application.dependency_overrides[get_settings] = lambda: settings
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def anon(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def client(anon):
    resp = await anon.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return anon


AGENT = {
    "name": "Support",
    "prompt": "You help {{customer_name}} with order {{order_id}}.",
    "greeting": "Hi {{customer_name}}!",
    "voice": "Kore",
    "variables": [{"name": "customer_name", "default": "there"}, {"name": "order_id"}],
    "tools": [
        {
            "name": "check_order",
            "description": "Looks up an order",
            "url": "https://tools.example/orders",
            "parameters": [{"name": "order_id", "type": "string", "required": True}],
        }
    ],
}


@pytest.fixture
async def agent(client) -> dict:
    resp = await client.post("/api/agents", json=AGENT)
    assert resp.status_code == 201, resp.text
    return resp.json()
