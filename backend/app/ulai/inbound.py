"""Answers inbound phone calls: subscribes to the calls Ulai assigns to our agents."""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..models import Trunk, TrunkDirection
from .calls import CallManager
from .gateway import Gateway

log = logging.getLogger(__name__)


class InboundListener:
    def __init__(self, gateway: Gateway, db: async_sessionmaker[AsyncSession], calls: CallManager):
        self.gateway = gateway
        self.db = db
        self.calls = calls
        self.state = "idle"  # idle | running | error
        self.last_error = ""
        self._changed = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    def refresh(self) -> None:
        """Call after inbound routing changes, so the subscription covers the right agents."""
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
        self.state, self.last_error = "running", ""
        async for a in self.gateway.assignments(agent_ids):
            try:
                await self.calls.accept_inbound(a.session_id, a.call)
            except Exception:
                log.exception("couldn't take inbound call %s", a.session_id)
