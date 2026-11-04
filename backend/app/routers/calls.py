import asyncio
import csv
import io
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import schemas
from ..auth import require_admin
from ..db import get_db
from ..deps import Services, services
from ..models import Agent, Call, CallDirection, CallStatus, Opening, Trunk, TrunkDirection
from ..ulai.gateway import UlaiError
from ..ulai.hub import ALL

router = APIRouter(prefix="/api/calls", tags=["calls"], dependencies=[Depends(require_admin)])

KEEPALIVE_SECONDS = 15


def _filtered(
    stmt: Select,
    status_: CallStatus | None,
    direction: CallDirection | None,
    agent_id: str | None,
    q: str | None,
) -> Select:
    if status_:
        stmt = stmt.where(Call.status == status_)
    if direction:
        stmt = stmt.where(Call.direction == direction)
    if agent_id:
        stmt = stmt.where(Call.agent_id == agent_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Call.to_number.ilike(like),
                Call.from_number.ilike(like),
                Call.agent_name.ilike(like),
                Call.id.ilike(like),
            )
        )
    return stmt


async def _agent(db: AsyncSession, agent_id: str) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    return agent


@router.get("", response_model=schemas.CallPage)
async def list_calls(
    status_: CallStatus | None = Query(None, alias="status"),
    direction: CallDirection | None = None,
    agent_id: str | None = None,
    q: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    total = await db.scalar(
        _filtered(select(func.count()).select_from(Call), status_, direction, agent_id, q)
    )
    rows = await db.scalars(
        _filtered(select(Call), status_, direction, agent_id, q)
        .order_by(Call.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return schemas.CallPage(items=list(rows), total=total or 0, page=page, page_size=page_size)


@router.get("/export.csv")
async def export_calls(
    status_: CallStatus | None = Query(None, alias="status"),
    direction: CallDirection | None = None,
    agent_id: str | None = None,
    q: str | None = Query(None, max_length=100),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.scalars(
            _filtered(select(Call), status_, direction, agent_id, q)
            .order_by(Call.created_at.desc())
            .limit(10_000)
        )
    ).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["id", "created_at", "direction", "status", "agent", "from", "to", "duration_seconds", "end_reason"]
    )
    for c in rows:
        w.writerow(
            [
                c.id,
                c.created_at.isoformat(),
                c.direction.value,
                c.status.value,
                c.agent_name,
                c.from_number,
                c.to_number,
                c.duration_seconds or 0,
                c.end_reason,
            ]
        )
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="calls.csv"'},
    )


@router.get("/live")
async def live_all(request: Request, svc: Services = Depends(services)):
    """Every call's updates, for lists and the overview."""
    return _sse(request, svc, ALL)


@router.get("/{call_id}", response_model=schemas.CallDetail)
async def get_call(call_id: str, db: AsyncSession = Depends(get_db)):
    call = await db.scalar(select(Call).where(Call.id == call_id).options(selectinload(Call.events)))
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call not found")
    return call


@router.get("/{call_id}/live")
async def live_call(call_id: str, request: Request, svc: Services = Depends(services)):
    return _sse(request, svc, call_id)


@router.post("/web", response_model=schemas.WebCallOut)
async def start_web_call(
    body: schemas.WebCallIn, db: AsyncSession = Depends(get_db), svc: Services = Depends(services)
):
    agent = await _agent(db, body.agent_id)
    if body.draft is not None:
        # A transient copy carrying the unsaved edits; it's never added to the session, so never saved.
        draft = body.draft.model_dump(mode="json")
        agent = Agent(id=agent.id, **draft | {"opening": Opening(draft["opening"])})
    try:
        return await svc.calls.start_web_call(agent, body.variables)
    except UlaiError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Couldn't start the call: {err}") from err


@router.post("/outbound", response_model=schemas.CallOut, status_code=status.HTTP_201_CREATED)
async def start_outbound_call(
    body: schemas.OutboundCallIn, db: AsyncSession = Depends(get_db), svc: Services = Depends(services)
):
    agent = await _agent(db, body.agent_id)
    trunk = await db.get(Trunk, body.trunk_id)
    if trunk is None or trunk.direction != TrunkDirection.OUTBOUND:
        raise HTTPException(422, "Choose an outbound trunk")
    if not trunk.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{trunk.name} is disabled")
    from_number = body.from_number or (trunk.numbers or [None])[0]
    if not from_number:
        raise HTTPException(422, f"{trunk.name} has no caller ID number")
    if from_number not in (trunk.numbers or []):
        raise HTTPException(422, f"{from_number} isn't a number on {trunk.name}")
    try:
        return await svc.calls.start_outbound_call(agent, trunk, body.to_number, from_number, body.variables)
    except UlaiError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err


@router.post("/{call_id}/end", response_model=schemas.CallOut)
async def end_call(call_id: str, svc: Services = Depends(services)):
    try:
        return await svc.calls.end_call(call_id)
    except LookupError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call not found") from err


def _sse(request: Request, svc: Services, topic: str) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        q = svc.hub.subscribe(topic)
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(msg)}\n\n"
        finally:
            svc.hub.unsubscribe(topic, q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        # no-transform and X-Accel-Buffering stop proxies from buffering the stream.
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
