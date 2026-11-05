"""Starts calls on Ulai and follows each one live until it ends.

Every call, web, outbound or inbound, puts the agent into the call's session with ulai-agents. Each call
then gets a monitor task that:
  * attaches to the agent: transcript, usage, the end of the call, answering its tools as they're called;
  * for phone calls, also watches the session on the control plane, to see the callee pick up or hang up;
  * for outbound calls, ends the call if nobody answers within the ring timeout.
Everything worth keeping is written to the database and published to the Hub for the UI.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import ulai_agents as ua
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .. import schemas
from ..config import Settings
from ..models import (
    ACTIVE_CALL_STATUSES,
    Agent,
    Call,
    CallDirection,
    CallEvent,
    CallEventKind,
    CallStatus,
    Trunk,
)
from .gateway import CallGone, Gateway, UlaiError, quietly
from .hub import Hub
from .profile import ToolAnswer, build_agent, build_tools, builtins, call_variables
from .tools import run_tool

log = logging.getLogger(__name__)

# Attempts to (re)attach to a call's agent before giving up on following it.
ATTACH_ATTEMPTS = 6
# After the caller hangs up, how long to wait for the agent to report the end before ending it ourselves.
HANGUP_GRACE_SECONDS = 8


def _now() -> datetime:
    return datetime.now(UTC)


def _ms(elapsed: timedelta) -> int | None:
    return int(elapsed.total_seconds() * 1000) if elapsed else None


class CallManager:
    def __init__(self, gateway: Gateway, settings: Settings, db: async_sessionmaker[AsyncSession], hub: Hub):
        self.gateway = gateway
        self.settings = settings
        self.db = db
        self.hub = hub
        self.http = httpx.AsyncClient(follow_redirects=False)
        self._monitors: dict[str, asyncio.Task] = {}
        self._seq: dict[str, int] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------ starting calls

    async def start_web_call(self, agent: Agent, variables: dict[str, str]) -> schemas.WebCallOut:
        call = await self._new_call(agent, CallDirection.WEB, variables=variables)
        values = call_variables(agent, variables, builtins(direction="web"))
        try:
            ua_agent = build_agent(agent, self.settings, values, direction="web")
            session_id = await self._open_session(call, ua_agent)
            join = await self.gateway.join_user(session_id, participant_id=f"web-{call.id[:8]}")
        except UlaiError as err:
            await self._fail(call.id, str(err))
            raise
        self._spawn(call.id, session_id, agent.tools, phone=False)
        return schemas.WebCallOut(
            call_id=call.id,
            session_id=session_id,
            participant_id=join.participant_id,
            ticket=join.ticket,
            node_address=join.node_address,
            events_token=join.events_token,
            control_plane_url=self.settings.ulai_cp_url,
            ice_servers=self.settings.ice_servers(),
        )

    async def start_outbound_call(
        self, agent: Agent, trunk: Trunk, to_number: str, from_number: str, variables: dict[str, str]
    ) -> Call:
        call = await self._new_call(
            agent,
            CallDirection.OUTBOUND,
            variables=variables,
            trunk_id=trunk.id,
            from_number=from_number,
            to_number=to_number,
        )
        values = call_variables(agent, variables, builtins(direction="outbound", to_number=to_number))
        try:
            session_id = await self._open_session(
                call, build_agent(agent, self.settings, values, direction="outbound")
            )
        except UlaiError as err:
            await self._fail(call.id, str(err))
            raise
        # Follow the call before dialling, so we can't miss the pick-up.
        self._spawn(call.id, session_id, agent.tools, phone=True)
        try:
            await self.gateway.originate(
                session_id=session_id,
                trunk_id=trunk.ulai_trunk_id,
                to_number=to_number,
                from_number=from_number,
            )
        except UlaiError as err:
            await self._fail(call.id, f"Couldn't place the call: {err}")
            await quietly(self.gateway.terminate_session(session_id))
            raise
        await self._set_status(call.id, CallStatus.RINGING, f"Dialling {to_number}")
        return await self._get(call.id)

    async def accept_inbound(self, session_id: str, agent_id: str, from_number: str, to_number: str) -> bool:
        """Answers a phone call a dispatch rule routed to one of our agents, now that its caller is in the
        session: puts the agent in, as for an outbound call. False when it isn't ours to answer."""
        async with self.db() as db:
            agent = await db.get(Agent, agent_id)
            if agent is None:
                log.info("inbound call %s is for agent %s, which isn't one of ours", session_id, agent_id)
                return False
            existing = await db.scalar(select(Call).where(Call.session_id == session_id))
            if existing is not None:
                return False
            trunk = await self._trunk_for_number(db, to_number)
        call = await self._new_call(
            agent,
            CallDirection.INBOUND,
            session_id=session_id,
            trunk_id=trunk.id if trunk else None,
            from_number=from_number,
            to_number=to_number,
            status=CallStatus.IN_PROGRESS,
            answered=True,
        )
        await self._add_event(call.id, CallEventKind.STATUS, text=f"Incoming call from {from_number}")
        values = call_variables(
            agent, {}, builtins(direction="inbound", from_number=from_number, to_number=to_number)
        )
        try:
            ua_agent = build_agent(agent, self.settings, values, direction="inbound")
            await self._join_agent(call, ua_agent, session_id)
        except UlaiError as err:
            # Nobody will answer the caller; hang up rather than leave them in silence.
            await quietly(self.gateway.terminate_session(session_id))
            await self._fail(call.id, f"Couldn't start the agent: {err}")
            return True
        self._spawn(call.id, session_id, agent.tools, phone=True)
        return True

    async def end_call(self, call_id: str) -> Call:
        call = await self._get(call_id)
        if call.status.is_final:
            return call
        if call.session_id:
            if call.agent_participant_id:
                await quietly(self.gateway.leave_agent(call.session_id, call.agent_participant_id, "ended"))
            await quietly(self.gateway.terminate_session(call.session_id))
        # The monitor usually records the end; this covers a call that never got that far.
        await asyncio.sleep(0)
        await self._finish(call_id, reason="Ended from the studio")
        return await self._get(call_id)

    # ------------------------------------------------------------------ lifecycle

    async def resume(self) -> None:
        """After a restart, picks the in-flight calls back up (or closes them if they're gone)."""
        async with self.db() as db:
            rows = (await db.scalars(select(Call).where(Call.status.in_(ACTIVE_CALL_STATUSES)))).all()
            pending = [(c.id, c.session_id, c.agent_id, c.direction) for c in rows]
        for call_id, session_id, agent_id, direction in pending:
            if not session_id:
                await self._finish(
                    call_id, reason="The studio restarted before the call connected", failed=True
                )
                continue
            async with self.db() as db:
                agent = await db.get(Agent, agent_id) if agent_id else None
            tools = agent.tools if agent else []
            self._spawn(call_id, session_id, tools, phone=direction != CallDirection.WEB)

    async def shutdown(self) -> None:
        # Detaching doesn't end calls; they carry on and are resumed on the next start.
        for task in self._monitors.values():
            task.cancel()
        await asyncio.gather(*self._monitors.values(), return_exceptions=True)
        await self.http.aclose()

    def active_monitors(self) -> int:
        return len(self._monitors)

    # ------------------------------------------------------------------ internals: setup

    async def _new_call(
        self,
        agent: Agent,
        direction: CallDirection,
        *,
        status=CallStatus.QUEUED,
        answered: bool = False,
        **fields: Any,
    ) -> Call:
        async with self.db() as db:
            call = Call(
                agent_id=agent.id,
                agent_name=agent.name,
                direction=direction,
                status=status,
                answered_at=_now() if answered else None,
                **fields,
            )
            db.add(call)
            await db.commit()
            await db.refresh(call)
        self._publish_call(call)
        return call

    async def _open_session(self, call: Call, agent: ua.Agent) -> str:
        """Creates the call's session and puts the agent in it."""
        session_id = await self.gateway.create_session(
            {
                "call_id": call.id,
                "agent_id": agent.id,
                "direction": call.direction.value,
                "app": "ulai-voice-studio",
            }
        )
        try:
            await self._join_agent(call, agent, session_id)
        except UlaiError:
            await quietly(self.gateway.terminate_session(session_id))
            raise
        return session_id

    async def _join_agent(self, call: Call, agent: ua.Agent, session_id: str) -> None:
        participant = f"agent-{call.id[:8]}"
        async with self.db() as db:
            await db.execute(
                update(Call)
                .where(Call.id == call.id)
                .values(session_id=session_id, agent_participant_id=participant)
            )
            await db.commit()
        await self.gateway.join_agent(
            session_id,
            agent,
            participant_id=participant,
            fields={"call_id": call.id, "direction": call.direction.value, **(call.variables or {})},
        )

    def _spawn(self, call_id: str, session_id: str, tools: list, *, phone: bool) -> None:
        task = asyncio.create_task(self._monitor(call_id, session_id, tools or [], phone))
        self._monitors[call_id] = task
        task.add_done_callback(lambda _t: self._monitors.pop(call_id, None))

    # ------------------------------------------------------------------ internals: monitoring

    async def _monitor(self, call_id: str, session_id: str, tools: list, phone: bool) -> None:
        helpers: list[asyncio.Task] = []
        try:
            if phone:
                helpers.append(asyncio.create_task(self._watch_session(call_id, session_id)))
            call = await self._get(call_id)
            if call.direction == CallDirection.OUTBOUND:
                helpers.append(asyncio.create_task(self._ring_timeout(call_id, session_id)))
            await self._follow_agent(call_id, session_id, tools)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("monitor for call %s crashed", call_id)
            await self._finish(call_id, reason="Lost track of the call", failed=True)
        finally:
            for t in helpers:
                t.cancel()

    async def _follow_agent(self, call_id: str, session_id: str, tools: list) -> None:
        attempt = 0
        while attempt < ATTACH_ATTEMPTS:
            if (await self._get(call_id)).status.is_final:
                return
            session = None
            try:
                # A re-attach doesn't replay what was said while we were away: ulai-agents can't replay
                # history to a client that answers tools, since that would answer past tool calls again.
                answered = build_tools(tools, self._tool_answer(call_id))
                session = await self.gateway.attach(session_id, answered)
                await self._connected(call_id)
                async for ev in session.events():
                    attempt = 0
                    if await self._on_agent_event(call_id, ev):
                        return
                # The events ended without an Ended event: the stream dropped.
            except asyncio.CancelledError:
                raise
            except CallGone as err:
                await self._finish(call_id, reason=str(err), failed=err.failed)
                return
            except Exception as err:
                log.info("agent session for call %s: %s", call_id, err)
            finally:
                if session is not None:
                    await session.close()
            attempt += 1
            await asyncio.sleep(min(2**attempt, 15))
        await self._finish(call_id, reason="Lost connection to the agent", failed=True)

    async def _connected(self, call_id: str) -> None:
        """A web call is live once we're attached to its agent; a phone call, once its callee answers."""
        call = await self._get(call_id)
        if call.direction == CallDirection.WEB and call.status != CallStatus.IN_PROGRESS:
            await self._set_status(call_id, CallStatus.IN_PROGRESS, "Connected", answered=True)

    async def _on_agent_event(self, call_id: str, ev: Any) -> bool:
        """Handles one ulai_agents event; returns True once the call has ended."""
        elapsed = _ms(ev.elapsed)
        if isinstance(ev, ua.Transcript):
            speaker = ev.speaker.value if ev.speaker else "unknown"
            if not ev.text.strip():
                pass
            elif ev.final:
                await self._add_event(
                    call_id,
                    CallEventKind.TRANSCRIPT,
                    speaker=speaker,
                    text=ev.text.strip(),
                    elapsed_ms=elapsed,
                )
            else:
                self.hub.publish(
                    call_id, {"type": "interim", "call_id": call_id, "speaker": speaker, "text": ev.text}
                )
        elif isinstance(ev, ua.StateChanged):
            if ev.state:
                state = {"type": "agent_state", "call_id": call_id, "state": ev.state.value}
                self.hub.publish(call_id, state)
        elif isinstance(ev, ua.Usage):
            await self._update(
                call_id,
                usage={
                    "prompt_tokens": ev.prompt_total,
                    "response_tokens": ev.response_total,
                    "cached_tokens": ev.prompt_cached,
                },
            )
        elif isinstance(ev, ua.ToolOutcome):
            # One of Ulai's own tools, such as ending the call. Ours are recorded as they're answered.
            await self._add_event(
                call_id,
                CallEventKind.TOOL_CALL,
                text=ev.name,
                elapsed_ms=elapsed,
                data={"arguments": ev.args, "result": ev.result, "ok": not ev.error, "by": "ulai"},
            )
        elif isinstance(ev, ua.Rejected):
            log.warning("Ulai refused %s on call %s: %s", ev.command or "a command", call_id, ev.message)
        elif isinstance(ev, ua.Ended):
            await self._finish(call_id, reason=ev.reason or ev.end_reason, disposition=ev.disposition)
            return True
        return False

    def _tool_answer(self, call_id: str) -> ToolAnswer:
        """Answers this call's tools by calling their webhooks, and records each answer."""

        async def answer(tool: dict, args: dict[str, Any]) -> dict:
            started = asyncio.get_running_loop().time()
            call = await self._get(call_id)
            context = {
                "call_id": call_id,
                "direction": call.direction.value,
                "from_number": call.from_number,
                "to_number": call.to_number,
                "variables": call.variables,
            }
            result = await run_tool(self.http, tool, args, context)
            took = int((asyncio.get_running_loop().time() - started) * 1000)
            await self._add_event(
                call_id,
                CallEventKind.TOOL_CALL,
                text=tool["name"],
                data={"arguments": args, "result": result, "duration_ms": took, "ok": "error" not in result},
            )
            return result

        return answer

    async def _watch_session(self, call_id: str, session_id: str) -> None:
        """Follows the phone leg on the control plane: pick-up and hang-up."""
        last_id: str | None = None
        for attempt in range(ATTACH_ATTEMPTS):
            try:
                async for msg in self.gateway.session_events(session_id, last_id):
                    last_id = msg.get("id") or last_id
                    if await self._on_session_event(call_id, session_id, msg):
                        return
            except asyncio.CancelledError:
                raise
            except Exception as err:
                log.info("session watch for call %s: %s", call_id, err)
            await asyncio.sleep(min(2 ** (attempt + 1), 15))

    async def _on_session_event(self, call_id: str, session_id: str, msg: dict) -> bool:
        kind = msg.get("type")
        is_phone = msg.get("kind") == "SIP"
        if kind == "roster":
            if any(p.get("kind") == "SIP" for p in msg.get("participants", [])):
                await self._answered(call_id)
        elif kind in ("participant_joined", "participant_connected") and is_phone:
            await self._answered(call_id)
        elif kind == "participant_left" and is_phone:
            await self._add_event(call_id, CallEventKind.STATUS, text="Caller hung up")
            asyncio.create_task(self._end_after_grace(call_id, session_id))
        elif kind == "session_terminated":
            await self._finish(call_id, reason=msg.get("reason") or "Session ended")
            return True
        return False

    async def _answered(self, call_id: str) -> None:
        call = await self._get(call_id)
        if call.status in (CallStatus.QUEUED, CallStatus.RINGING):
            await self._set_status(call_id, CallStatus.IN_PROGRESS, "Answered", answered=True)

    async def _end_after_grace(self, call_id: str, session_id: str) -> None:
        await asyncio.sleep(HANGUP_GRACE_SECONDS)
        if not (await self._get(call_id)).status.is_final:
            await quietly(self.gateway.terminate_session(session_id))
            await self._finish(call_id, reason="Caller hung up")

    async def _ring_timeout(self, call_id: str, session_id: str) -> None:
        await asyncio.sleep(self.settings.ring_timeout_seconds)
        call = await self._get(call_id)
        if call.status in (CallStatus.QUEUED, CallStatus.RINGING):
            await quietly(self.gateway.terminate_session(session_id))
            await self._finish(call_id, reason=f"No answer after {self.settings.ring_timeout_seconds}s")

    # ------------------------------------------------------------------ internals: persistence

    def _lock(self, call_id: str) -> asyncio.Lock:
        return self._locks.setdefault(call_id, asyncio.Lock())

    async def _get(self, call_id: str) -> Call:
        async with self.db() as db:
            call = await db.get(Call, call_id)
            if call is None:
                raise LookupError(call_id)
            return call

    async def _update(self, call_id: str, **values: Any) -> Call:
        async with self.db() as db:
            await db.execute(update(Call).where(Call.id == call_id).values(**values))
            await db.commit()
            call = await db.get(Call, call_id, populate_existing=True)
        self._publish_call(call)
        return call

    async def _set_status(
        self, call_id: str, status: CallStatus, note: str, *, answered: bool = False
    ) -> None:
        async with self._lock(call_id):
            call = await self._get(call_id)
            if call.status.is_final or call.status == status:
                return
            values: dict[str, Any] = {"status": status}
            if answered and call.answered_at is None:
                values["answered_at"] = _now()
            await self._update(call_id, **values)
        await self._add_event(call_id, CallEventKind.STATUS, text=note)

    async def _finish(
        self, call_id: str, *, reason: str = "", disposition: str = "", failed: bool = False
    ) -> None:
        async with self._lock(call_id):
            call = await self._get(call_id)
            if call.status.is_final:
                return
            ended = _now()
            if failed:
                status = CallStatus.FAILED
            elif call.answered_at is None and call.direction == CallDirection.OUTBOUND:
                status = CallStatus.NO_ANSWER
            else:
                status = CallStatus.COMPLETED
            answered = call.answered_at
            if answered is not None and answered.tzinfo is None:
                answered = answered.replace(tzinfo=UTC)
            duration = int((ended - answered).total_seconds()) if answered else 0
            values: dict[str, Any] = {
                "status": status,
                "ended_at": ended,
                "duration_seconds": max(duration, 0),
                "end_reason": reason[:255],
                "disposition": disposition[:64],
            }
            if failed:
                values["error"] = reason
            await self._update(call_id, **values)
        label = {
            CallStatus.COMPLETED: "Call ended",
            CallStatus.NO_ANSWER: "No answer",
            CallStatus.FAILED: "Call failed",
        }[status]
        await self._add_event(call_id, CallEventKind.STATUS, text=f"{label}{f': {reason}' if reason else ''}")
        if (task := self._monitors.get(call_id)) and task is not asyncio.current_task():
            task.cancel()
        self._locks.pop(call_id, None)

    async def _fail(self, call_id: str, error: str) -> None:
        await self._finish(call_id, reason=error, failed=True)

    async def _add_event(
        self,
        call_id: str,
        kind: CallEventKind,
        *,
        speaker: str = "",
        text: str = "",
        data: dict | None = None,
        elapsed_ms: int | None = None,
    ) -> None:
        async with self.db() as db:
            if call_id not in self._seq:
                self._seq[call_id] = await db.scalar(
                    select(func.coalesce(func.max(CallEvent.seq), 0)).where(CallEvent.call_id == call_id)
                )
            self._seq[call_id] += 1
            ev = CallEvent(
                call_id=call_id,
                seq=self._seq[call_id],
                kind=kind,
                speaker=speaker,
                text=text,
                data=data or {},
                elapsed_ms=elapsed_ms,
            )
            db.add(ev)
            await db.commit()
            await db.refresh(ev)
        self.hub.publish(
            call_id,
            {
                "type": "event",
                "call_id": call_id,
                "event": schemas.CallEventOut.model_validate(ev).model_dump(mode="json"),
            },
        )

    def _publish_call(self, call: Call) -> None:
        self.hub.publish(
            call.id, {"type": "call", "call": schemas.CallOut.model_validate(call).model_dump(mode="json")}
        )

    async def _trunk_for_number(self, db: AsyncSession, number: str) -> Trunk | None:
        trunks = (await db.scalars(select(Trunk).where(Trunk.direction == "inbound"))).all()
        return next((t for t in trunks if number in (t.numbers or [])), None)
