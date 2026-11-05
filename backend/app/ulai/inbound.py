"""Answers inbound phone calls.

A trunk's dispatch rule names the studio agent for its numbers. When a call arrives, Ulai's SIP gateway puts
the caller into a new session, carrying that agent in its join metadata; the control plane announces the
join on our project's event feed, and the studio puts the agent into the session, as for an outbound call.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..models import Trunk, TrunkDirection
from .calls import CallManager
from .gateway import AGENT_METADATA_KEY, Gateway

log = logging.getLogger(__name__)

# Where an inbound caller's join metadata names the agent: the SIP gateway sets assigned_agent from the
# rule's agent_name; the rule's dispatch_metadata carries AGENT_METADATA_KEY too.
_AGENT_KEYS = ("assigned_agent", AGENT_METADATA_KEY)


def inbound_call(msg: dict) -> tuple[str, str, str, str] | None:
    """(session_id, agent_id, from_number, to_number) when msg is a phone caller arriving for an agent."""
    meta = msg.get("metadata") or {}
    if msg.get("type") != "participant_joined" or msg.get("kind") != "SIP":
        return None
    if msg.get("sip_direction") != "INBOUND" and meta.get("direction") != "inbound":
        return None
    agent_id = next((meta[k] for k in _AGENT_KEYS if meta.get(k)), "")
    if not agent_id or not msg.get("session_id"):
        return None
    # The caller's number, and the number they dialled.
    return msg["session_id"], agent_id, meta.get("caller_id", ""), meta.get("phone_number", "")


class InboundListener:
    def __init__(self, gateway: Gateway, db: async_sessionmaker[AsyncSession], calls: CallManager):
        self.gateway = gateway
        self.db = db
        self.calls = calls
        self.state = "idle"  # idle | running | error
        self.last_error = ""
        self._changed = asyncio.Event()
        self._task: asyncio.Task | None = None
        # The feed's last event, so a reconnect resumes without missing a call.
        self._last_event_id: str | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    def refresh(self) -> None:
        """Call after inbound routing changes, so the listener answers for the right agents."""
        self._changed.set()

    async def _agent_ids(self) -> list[str]:
        async with self.db() as db:
            rows = await db.scalars(
                select(Trunk.agent_id).where(
                    Trunk.direction == TrunkDirection.INBOUND,
                    Trunk.enabled.is_(True),
                    Trunk.agent_id.is_not(None),
                )
            )
            return sorted(set(rows))

    async def _run(self) -> None:
        backoff = 1
        while True:
            self._changed.clear()
            agent_ids = await self._agent_ids()
            if not agent_ids:
                self.state = "idle"
                await self._changed.wait()
                continue
            listen = asyncio.create_task(self._listen(agent_ids))
            changed = asyncio.create_task(self._changed.wait())
            done, _ = await asyncio.wait({listen, changed}, return_when=asyncio.FIRST_COMPLETED)
            for t in (listen, changed):
                t.cancel()
            await asyncio.gather(listen, changed, return_exceptions=True)
            if changed in done:
                backoff = 1
                continue
            # The subscription ended or failed; retry with backoff.
            err = listen.exception() if not listen.cancelled() else None
            if err:
                self.state, self.last_error = "error", str(err)
                log.warning("inbound subscription failed: %s", err)
            # Wait before retrying, but a routing change (e.g. the last agent unassigned) ends the wait early.
            try:
                await asyncio.wait_for(self._changed.wait(), timeout=backoff)
                backoff = 1
            except TimeoutError:
                backoff = min(backoff * 2, 30)

    async def _listen(self, agent_ids: list[str]) -> None:
        log.info("listening for inbound calls for %d agent(s)", len(agent_ids))
        ours = set(agent_ids)
        self.state, self.last_error = "running", ""
        async for msg in self.gateway.project_events(self._last_event_id):
            self._last_event_id = msg.get("id") or self._last_event_id
            call = inbound_call(msg)
            if call is None or call[1] not in ours:
                continue  # not a phone call, or another app's agent on the same project
            try:
                await self.calls.accept_inbound(*call)
            except Exception:
                log.exception("couldn't take inbound call %s", call[0])
