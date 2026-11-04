"""The one place that talks to Ulai Voice Infra, through the ulai-api Python SDK.

Everything else in the app goes through `Gateway`, so tests can swap in a fake.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import websockets

from ..config import Settings

log = logging.getLogger(__name__)


class UlaiError(Exception):
    """Ulai refused or failed a request; the message is safe to show the user."""


@dataclass
class UserJoin:
    session_id: str
    participant_id: str
    ticket: str
    node_address: str
    events_token: str | None


@dataclass
class RemoteTrunk:
    id: str


@dataclass
class RemoteRule:
    id: str


class AgentStream(Protocol):
    """A live connection to one call's agent: events in, control messages out."""

    def send(self, event: Any) -> None: ...
    def close(self) -> None: ...
    def __aiter__(self) -> AsyncIterator[Any]: ...


class Gateway(Protocol):
    project_id: str | None

    async def check(self) -> str: ...
    async def close(self) -> None: ...

    async def create_session(self, metadata: dict[str, str]) -> str: ...
    async def join_user(self, session_id: str, participant_id: str) -> UserJoin: ...
    async def join_agent(
        self,
        session_id: str,
        agent_id: str,
        participant_id: str,
        profile: dict,
        custom_fields: dict,
    ) -> None: ...
    async def leave_agent(self, session_id: str, participant_id: str, reason: str) -> None: ...
    async def terminate_session(self, session_id: str) -> None: ...
    async def watch_session(self, session_id: str) -> str: ...
    def session_events(self, session_id: str, last_event_id: str | None) -> AsyncIterator[dict]: ...
    async def originate(
        self, *, session_id: str, trunk_id: str, to_number: str, from_number: str
    ) -> None: ...

    def attach(self, session_id: str, profile: dict | None, tool_names: list[str]) -> AgentStream: ...
    def assignments(self, agent_ids: list[str]) -> AsyncIterator[Any]: ...

    async def create_inbound_trunk(
        self, name: str, numbers: list[str], allowed: list[str]
    ) -> RemoteTrunk: ...
    async def update_inbound_trunk(
        self, trunk_id: str, name: str, numbers: list[str], allowed: list[str]
    ) -> None: ...
    async def create_outbound_trunk(
        self, name: str, address: str, transport: str, username: str, password: str
    ) -> RemoteTrunk: ...
    async def update_outbound_trunk(self, trunk_id: str, **fields: Any) -> None: ...
    async def set_trunk_enabled(self, direction: str, trunk_id: str, enabled: bool) -> None: ...
    async def delete_trunk(self, direction: str, trunk_id: str) -> None: ...

    async def create_rule(self, name: str, agent_id: str, trunk_id: str) -> RemoteRule: ...
    async def update_rule(self, rule_id: str, agent_id: str) -> None: ...
    async def delete_rule(self, rule_id: str) -> None: ...


async def quietly(coro) -> None:
    """Awaits a best-effort cleanup call, logging rather than raising if it fails."""
    try:
        await coro
    except Exception as err:
        log.info("ignored during cleanup: %s", err)


def _describe(err: Exception) -> str:
    if isinstance(err, httpx.HTTPStatusError):
        body = err.response.text[:300]
        return f"Ulai returned {err.response.status_code}: {body}"
    if isinstance(err, httpx.HTTPError):
        return f"Couldn't reach Ulai: {err.__class__.__name__}"
    code = getattr(err, "code", None)
    if callable(code):  # grpc.aio.AioRpcError
        details = getattr(err, "details", lambda: "")()
        return f"Ulai agent service: {code().name} {details}".strip()
    return str(err) or err.__class__.__name__


class _SdkAgentStream:
    def __init__(self, sdk_agent: Any, first: Any, tool_names: list[str], pb: Any):
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._queue.put_nowait(first)
        if tool_names:
            self._queue.put_nowait(pb.ClientEvent(handled_tools=pb.HandledTools(names=tool_names)))
        self._call = sdk_agent.run(self._requests())

    async def _requests(self) -> AsyncIterator[Any]:
        while True:
            ev = await self._queue.get()
            if ev is None:
                return
            yield ev

    def send(self, event: Any) -> None:
        self._queue.put_nowait(event)

    def close(self) -> None:
        self._queue.put_nowait(None)
        self._call.cancel()

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._call.__aiter__()


class SdkGateway:
    """Gateway backed by the real ulai-api SDK."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.project_id: str | None = None
        self._client: Any = None
        self._lock = asyncio.Lock()
        self._http = httpx.AsyncClient(timeout=15)

    async def _ready(self) -> Any:
        if self._client is not None:
            return self._client
        async with self._lock:
            if self._client is not None:
                return self._client
            if not self.settings.ulai_api_key.get_secret_value():
                raise UlaiError("ULAI_API_KEY is not set")
            from ulai_api.client import UlaiClient

            s = self.settings
            client = UlaiClient(
                backend_url=s.ulai_api_url,
                control_plane_url=s.ulai_cp_url,
                agent_url=s.ulai_agent_url,
                api_key=s.ulai_api_key.get_secret_value(),
                agent_api_key=s.ulai_agent_api_key.get_secret_value() or None,
                system_secret=s.ulai_system_secret.get_secret_value() or None,
            )
            try:
                await client.__aenter__()
            except Exception as err:
                await client.aclose()
                raise UlaiError(_describe(err)) from err
            self._client = client
            self.project_id = client.project_id
            return client

    async def _do(self, fn, *args, **kwargs):
        client = await self._ready()
        try:
            return await fn(client, *args, **kwargs)
        except UlaiError:
            raise
        except Exception as err:
            raise UlaiError(_describe(err)) from err

    async def check(self) -> str:
        await self._ready()
        return self.project_id or ""

    async def close(self) -> None:
        await self._http.aclose()
        if self._client is not None:
            await self._client.aclose()

    # ----- sessions -----

    async def create_session(self, metadata: dict[str, str]) -> str:
        return await self._do(lambda c: c.sessions.create(max_participants=4, metadata=metadata))

    async def join_user(self, session_id: str, participant_id: str) -> UserJoin:
        info = await self._do(lambda c: c.sessions.join(session_id, participant_id=participant_id))
        return UserJoin(
            session_id=info.session_id,
            participant_id=info.connection_id,
            ticket=info.ticket,
            node_address=info.node.address,
            events_token=info.events_token,
        )

    async def join_agent(self, session_id, agent_id, participant_id, profile, custom_fields) -> None:
        await self._do(
            lambda c: c.agent.join_bridge(
                room=session_id,
                agent_id=agent_id,
                participant_id=participant_id,
                profile=profile,
                opening=profile.get("opening"),
                custom_fields=custom_fields,
            )
        )

    async def leave_agent(self, session_id, participant_id, reason) -> None:
        await self._do(lambda c: c.agent.leave_bridge(session_id, participant_id, reason=reason))

    async def terminate_session(self, session_id: str) -> None:
        async def go(c):
            try:
                await c.sessions.terminate(session_id)
            except httpx.HTTPStatusError as err:
                if err.response.status_code != 404:  # already gone
                    raise

        await self._do(go)

    async def watch_session(self, session_id: str) -> str:
        return await self._do(lambda c: c.sessions.watch(session_id))

    async def session_events(self, session_id: str, last_event_id: str | None) -> AsyncIterator[dict]:
        """The control plane's events for one session (participants joining and leaving, its end)."""
        token = await self.watch_session(session_id)
        base = self.settings.ulai_cp_url.replace("https://", "wss://").replace("http://", "ws://")
        async with websockets.connect(f"{base}/api/v1/events", open_timeout=10) as ws:
            sub = {"action": "subscribe", "scope": "session", "session_id": session_id, "token": token}
            if last_event_id:
                sub["last_event_id"] = last_event_id
            await ws.send(json.dumps(sub))
            async for raw in ws:
                yield json.loads(raw)

    async def originate(self, *, session_id, trunk_id, to_number, from_number) -> None:
        # The SDK's originate_call posts to a hard-coded address; this uses the configured one.
        client = await self._ready()
        headers = {"Authorization": f"Bearer {self.settings.ulai_api_key.get_secret_value()}"}
        if secret := self.settings.ulai_system_secret.get_secret_value():
            headers["X-System-Secret"] = secret
        payload = {
            "to_number": to_number,
            "trunk_id": trunk_id,
            "project_id": client.project_id,
            "from_number": from_number,
            "name": to_number,
            "offer_srtp": False,
            "require_srtp": False,
            "dial_verbatim": False,
            "session_id": session_id,
        }
        try:
            resp = await self._http.post(self.settings.ulai_sip_originate_url, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPError as err:
            raise UlaiError(_describe(err)) from err

    # ----- agent streams -----

    def attach(self, session_id: str, profile: dict | None, tool_names: list[str]) -> AgentStream:
        from ulai_api.proto import agent_session_pb2 as pb

        if self._client is None:
            raise UlaiError("Ulai client is not connected")
        attach = pb.Attach(session_id=session_id, replay_history=True)
        if profile:
            attach.profile.CopyFrom(profile_to_pb(profile, pb))
        first = pb.ClientEvent(attach=attach)
        return _SdkAgentStream(self._client.agent, first, tool_names, pb)

    async def assignments(self, agent_ids: list[str]) -> AsyncIterator[Any]:
        client = await self._ready()
        async for a in client.agent.subscribe(agent_ids=agent_ids, client_name="ulai-voice-studio"):
            yield a

    # ----- trunks -----

    async def create_inbound_trunk(self, name, numbers, allowed) -> RemoteTrunk:
        t = await self._do(
            lambda c: c.sip.create_inbound_trunk(
                name=name, numbers=numbers, allowed_addresses=allowed or None
            )
        )
        return RemoteTrunk(id=str(t.id))

    async def update_inbound_trunk(self, trunk_id, name, numbers, allowed) -> None:
        await self._do(
            lambda c: c.sip.update_inbound_trunk(
                trunk_id, name=name, numbers=numbers, allowed_addresses=allowed
            )
        )

    async def create_outbound_trunk(self, name, address, transport, username, password) -> RemoteTrunk:
        from ulai_api.models.sip import SIPTransport

        t = await self._do(
            lambda c: c.sip.create_outbound_trunk(
                name=name,
                address=address,
                transport=SIPTransport(transport),
                username=username or None,
                password=password or None,
            )
        )
        return RemoteTrunk(id=str(t.id))

    async def update_outbound_trunk(self, trunk_id, **fields) -> None:
        from ulai_api.models.sip import SIPTransport

        if fields.get("transport"):
            fields["transport"] = SIPTransport(fields["transport"]).value
        await self._do(lambda c: c.sip.update_outbound_trunk(trunk_id, **fields))

    async def set_trunk_enabled(self, direction, trunk_id, enabled) -> None:
        if direction == "inbound":
            await self._do(lambda c: c.sip.set_inbound_trunk_enabled(trunk_id, enabled))
        else:
            await self._do(lambda c: c.sip.set_outbound_trunk_enabled(trunk_id, enabled))

    async def delete_trunk(self, direction, trunk_id) -> None:
        async def go(c):
            fn = c.sip.delete_inbound_trunk if direction == "inbound" else c.sip.delete_outbound_trunk
            try:
                await fn(trunk_id)
            except httpx.HTTPStatusError as err:
                if err.response.status_code != 404:
                    raise

        await self._do(go)

    # ----- inbound routing -----

    async def create_rule(self, name, agent_id, trunk_id) -> RemoteRule:
        r = await self._do(
            lambda c: c.dispatch.create_rule(name=name, agent_name=agent_id, trunk_ids=[trunk_id])
        )
        return RemoteRule(id=str(r.id))

    async def update_rule(self, rule_id, agent_id) -> None:
        await self._do(lambda c: c.dispatch.update_rule(rule_id, agent_name=agent_id))

    async def delete_rule(self, rule_id) -> None:
        async def go(c):
            try:
                await c.dispatch.delete_rule(rule_id)
            except httpx.HTTPStatusError as err:
                if err.response.status_code != 404:
                    raise

        await self._do(go)


def profile_to_pb(profile: dict, pb: Any) -> Any:
    """Builds an AgentProfile message from the same dict join_bridge takes."""
    out = pb.AgentProfile()
    for field in (
        "prompt",
        "greeting",
        "closing",
        "voice",
        "model",
        "language",
        "ai_backend",
        "gemini_project_id",
        "gemini_location",
        "google_credentials_json",
    ):
        if profile.get(field):
            setattr(out, field, str(profile[field]))
    for field in (
        "allow_interruptions",
        "greeting_interruptible",
        "backchannel_gate",
        "silence_monitor",
        "background_noise",
        "live_transcription",
        "amd_enabled",
    ):
        if profile.get(field) is not None:
            setattr(out, field, bool(profile[field]))
    if profile.get("temperature") is not None:
        out.temperature = float(profile["temperature"])
    if profile.get("max_call_duration_seconds"):
        out.max_call_duration_seconds = int(profile["max_call_duration_seconds"])
    if profile.get("initial_engagement_deadline_ms"):
        out.initial_engagement_deadline_ms = int(profile["initial_engagement_deadline_ms"])
    opening = profile.get("opening")
    if opening == "caller":
        out.opening = pb.OpeningTurn.OPENING_TURN_CALLER
    elif opening == "agent":
        out.opening = pb.OpeningTurn.OPENING_TURN_AGENT
    for tool in profile.get("tools") or []:
        spec = out.tools.add(name=tool["name"], description=tool.get("description", ""))
        spec.required.extend(tool.get("required", []))
        for pname, p in (tool.get("parameters") or {}).items():
            param = spec.parameters[pname]
            param.type = p.get("type", "string")
            param.description = p.get("description", "")
            param.enum.extend(str(e) for e in p.get("enum", []))
    return out
