from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import schemas
from ..auth import require_admin
from ..db import get_db
from ..deps import Services, services
from ..models import Agent, Call, Trunk, TrunkDirection
from ..ulai.gateway import UlaiError

router = APIRouter(prefix="/api/agents", tags=["agents"], dependencies=[Depends(require_admin)])


async def _get(db: AsyncSession, agent_id: str) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    return agent


@router.get("", response_model=list[schemas.AgentSummary])
async def list_agents(db: AsyncSession = Depends(get_db)):
    agents = (await db.scalars(select(Agent).order_by(Agent.updated_at.desc()))).all()
    week_ago = datetime.now(UTC) - timedelta(days=7)
    totals = dict((await db.execute(select(Call.agent_id, func.count()).group_by(Call.agent_id))).all())
    recent = dict(
        (
            await db.execute(
                select(Call.agent_id, func.count()).where(Call.created_at >= week_ago).group_by(Call.agent_id)
            )
        ).all()
    )
    numbers: dict[str, list[str]] = {}
    for t in (await db.scalars(select(Trunk).where(Trunk.direction == TrunkDirection.INBOUND))).all():
        if t.agent_id:
            numbers.setdefault(t.agent_id, []).extend(t.numbers or [])
    return [
        schemas.AgentSummary.model_validate(a).model_copy(
            update={
                "calls_total": totals.get(a.id, 0),
                "calls_last_7d": recent.get(a.id, 0),
                "inbound_numbers": numbers.get(a.id, []),
            }
        )
        for a in agents
    ]


@router.post("", response_model=schemas.AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(body: schemas.AgentIn, db: AsyncSession = Depends(get_db)):
    agent = Agent(**body.model_dump(mode="json"))
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=schemas.AgentOut)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    return await _get(db, agent_id)


@router.put("/{agent_id}", response_model=schemas.AgentOut)
async def update_agent(agent_id: str, body: schemas.AgentIn, db: AsyncSession = Depends(get_db)):
    agent = await _get(db, agent_id)
    for key, value in body.model_dump(mode="json").items():
        setattr(agent, key, value)
    await db.commit()
    await db.refresh(agent)
    return agent


@router.post("/{agent_id}/duplicate", response_model=schemas.AgentOut, status_code=status.HTTP_201_CREATED)
async def duplicate_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    source = schemas.AgentIn.model_validate(await _get(db, agent_id), from_attributes=True)
    copy = Agent(**source.model_dump(mode="json") | {"name": f"{source.name} (copy)"[:120]})
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    return copy


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db), svc: Services = Depends(services)):
    agent = await _get(db, agent_id)
    # Stop routing calls to it first, so no number is left pointing at a deleted agent.
    for trunk in (await db.scalars(select(Trunk).where(Trunk.agent_id == agent.id))).all():
        if trunk.ulai_rule_id:
            try:
                await svc.gateway.delete_rule(trunk.ulai_rule_id)
            except UlaiError as err:
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY, f"Couldn't unassign {trunk.name}: {err}"
                ) from err
        trunk.agent_id = None
        trunk.ulai_rule_id = None
    await db.delete(agent)
    await db.commit()
    svc.inbound.refresh()
