"""The one place that talks to Ulai Voice Infra: sessions, trunks and routing through the ulai-api SDK,
agents through the ulai-agents SDK.

Everything else in the app goes through `Gateway`, so tests can swap in a fake.
"""

import asyncio
import ipaddress
import json
import logging
import urllib.parse
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import ulai_agents as ua
import websockets

from ..config import Settings

log = logging.getLogger(__name__)

# Dispatch rule metadata naming the studio agent that answers the rule's calls.
AGENT_METADATA_KEY = "studio_agent_id"


class UlaiError(Exception):
    """Ulai refused or failed a request; the message is safe to show the user."""


class CallGone(UlaiError):
    """The call is over, or Ulai dropped it: following it again won't help."""

    def __init__(self, message: str, *, failed: bool):
        super().__init__(message)
        self.failed = failed


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


class AgentSession(Protocol):
    """One call's agent, attached: its ulai_agents events, with its tools answered in the background."""

    def events(self) -> AsyncIterator[Any]: ...
    async def close(self) -> None: ...


class Gateway(Protocol):
    project_id: str | None

    async def check(self) -> str: ...
    async def close(self) -> None: ...

    async def create_session(self, metadata: dict[str, str]) -> str: ...
    async def join_user(self, session_id: str, participant_id: str) -> UserJoin: ...
    async def join_agent(
        self, session_id: str, agent: ua.Agent, participant_id: str, fields: dict
    ) -> None: ...
    async def leave_agent(self, session_id: str, participant_id: str, reason: str) -> None: ...
    async def terminate_session(self, session_id: str) -> None: ...
    async def watch_session(self, session_id: str) -> str: ...
    def session_events(self, session_id: str, last_event_id: str | None) -> AsyncIterator[dict]: ...
    def project_events(self, last_event_id: str | None) -> AsyncIterator[dict]: ...
    async def originate(
        self, *, session_id: str, trunk_id: str, to_number: str, from_number: str
    ) -> None: ...

    async def attach(self, session_id: str, tools: list[ua.Tool]) -> AgentSession: ...

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
    if isinstance(err, ua.AgentError):
        return f"Ulai agent service: {err}"
    return str(err) or err.__class__.__name__


def agent_server_address(url: str) -> tuple[str, bool]:
    """The agent server's host:port from ULAI_AGENT_URL, and whether to use TLS.

    "https://host" and a bare "host:port" use TLS, except to this machine; "http://host:port" doesn't.
    """
    raw = url.strip().rstrip("/")
    if "://" in raw:
        parsed = urllib.parse.urlsplit(raw)
        tls = parsed.scheme != "http"
        return f"{parsed.hostname}:{parsed.port or (443 if tls else 80)}", tls
    host = raw.rsplit(":", 1)[0].strip("[]") if ":" in raw else raw
    return (raw if ":" in raw else f"{raw}:443"), not _is_local(host)


def _is_local(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _rule_metadata(agent_id: str) -> dict[str, str]:
    return {AGENT_METADATA_KEY: agent_id, "app": "ulai-voice-studio"}


class _SdkAgentSession:
    def __init__(self, session: ua.Session):
        self._session = session

    async def events(self) -> AsyncIterator[Any]:
        try:
            async for ev in self._session.events():
                yield ev
        except ua.CallLostError as err:
            raise CallGone(str(err), failed=True) from err
        except ua.AgentError as err:
            raise UlaiError(_describe(err)) from err

    async def close(self) -> None:
        await self._session.close()


class SdkGateway:
    """Gateway backed by the real ulai-api and ulai-agents SDKs."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.project_id: str | None = None
        self._client: Any = None
        self._lock = asyncio.Lock()
        self._agents: ua.Client | None = None

    def _agent_client(self) -> ua.Client:
        # ulai_agents.Client doesn't dial until first used, so making it here costs nothing.
        if self._agents is None:
            s = self.settings
            address, tls = agent_server_address(s.ulai_agent_url)
            key = s.ulai_agent_api_key.get_secret_value() or s.ulai_api_key.get_secret_value()
            # An explicit http:// URL means the operator trusts the network to the agent server.
            self._agents = ua.Client(address, api_key=key or None, tls=tls, insecure=not tls)
        return self._agents

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
                api_key=s.ulai_api_key.get_secret_value(),
                system_secret=s.ulai_system_secret.get_secret_value() or None,
                sip_originate_url=s.ulai_sip_originate_url,
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
        if self._agents is not None:
            await self._agents.close()
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

    async def join_agent(self, session_id, agent, participant_id, fields) -> None:
        s = self.settings
        # The agent server joins the session on the control plane with our key, as we would.
        room = ua.Room(id=session_id, url=s.ulai_cp_url, token=s.ulai_api_key.get_secret_value())
        try:
            # Models, voices and languages come from the agent editor: Ulai judges them, not this SDK.
            await self._agent_client().join(
                room, agent, participant_id=participant_id, fields=fields, allow_unlisted_values=True
            )
        except ua.AgentError as err:
            raise UlaiError(_describe(err)) from err

    async def leave_agent(self, session_id, participant_id, reason) -> None:
        try:
            await self._agent_client().leave(session_id, participant_id=participant_id, reason=reason)
        except ua.AgentError as err:
            raise UlaiError(_describe(err)) from err

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
        sub = {"action": "subscribe", "scope": "session", "session_id": session_id, "token": token}
        async for msg in self._events(sub, last_event_id):
            yield msg

    async def project_events(self, last_event_id: str | None) -> AsyncIterator[dict]:
        """The control plane's events for every session in our project, e.g. a phone call arriving."""
        key = self.settings.ulai_api_key.get_secret_value()
        if not key:
            raise UlaiError("ULAI_API_KEY is not set")
        async for msg in self._events({"action": "subscribe", "scope": "global", "key": key}, last_event_id):
            yield msg

    async def _events(self, sub: dict, last_event_id: str | None) -> AsyncIterator[dict]:
        base = self.settings.ulai_cp_url.replace("https://", "wss://").replace("http://", "ws://")
        async with websockets.connect(f"{base}/api/v1/events", open_timeout=10) as ws:
            if last_event_id:
                sub = {**sub, "last_event_id": last_event_id}
            await ws.send(json.dumps(sub))
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") == "error":
                    raise UlaiError(f"Ulai events: {msg.get('message') or 'subscription refused'}")
                yield msg

    async def originate(self, *, session_id, trunk_id, to_number, from_number) -> None:
        # Posts to ULAI_SIP_ORIGINATE_URL, which the client was made with.
        await self._do(
            lambda c: c.sip.originate_call(
                to_number=to_number,
                trunk_id=trunk_id,
                project_id=c.project_id,
                from_number=from_number,
                name=to_number,
                offer_srtp=False,
                require_srtp=False,
                dial_verbatim=False,
                session_id=session_id,
            )
        )

    # ----- following a call's agent -----

    async def attach(self, session_id: str, tools: list[ua.Tool]) -> AgentSession:
        # Without history: ulai-agents won't replay past tool calls to a client that answers tools.
        try:
            session = await self._agent_client().attach(session_id, tools=tools)
        except (ua.NotFoundError, ua.CallEndedError) as err:
            raise CallGone("The call has already ended", failed=False) from err
        except ua.AgentError as err:
            raise UlaiError(_describe(err)) from err
        return _SdkAgentSession(session)

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

    # The rule names our agent; when its call arrives, the studio puts that agent into the session.
    async def create_rule(self, name, agent_id, trunk_id) -> RemoteRule:
        r = await self._do(
            lambda c: c.dispatch.create_rule(
                name=name,
                agent_name=agent_id,
                dispatch_metadata=_rule_metadata(agent_id),
                trunk_ids=[trunk_id],
            )
        )
        return RemoteRule(id=str(r.id))

    async def update_rule(self, rule_id, agent_id) -> None:
        await self._do(
            lambda c: c.dispatch.update_rule(
                rule_id, agent_name=agent_id, dispatch_metadata=_rule_metadata(agent_id)
            )
        )

    async def delete_rule(self, rule_id) -> None:
        async def go(c):
            try:
                await c.dispatch.delete_rule(rule_id)
            except httpx.HTTPStatusError as err:
                if err.response.status_code != 404:
                    raise

        await self._do(go)
