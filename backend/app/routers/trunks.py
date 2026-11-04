from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import schemas
from ..auth import require_admin
from ..db import get_db
from ..deps import Services, services
from ..models import Agent, Trunk, TrunkDirection
from ..ulai.gateway import UlaiError, quietly

router = APIRouter(prefix="/api/trunks", tags=["trunks"], dependencies=[Depends(require_admin)])


def _bad_gateway(err: UlaiError) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(err))


async def _get(db: AsyncSession, trunk_id: str) -> Trunk:
    # Reload so the joined agent reflects a reassignment made in this session.
    trunk = await db.get(Trunk, trunk_id, populate_existing=True)
    if trunk is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trunk not found")
    return trunk


async def _check_agent(db: AsyncSession, agent_id: str | None) -> None:
    if agent_id and await db.get(Agent, agent_id) is None:
        raise HTTPException(422, "That agent doesn't exist")


async def _check_numbers_free(db: AsyncSession, numbers: list[str], exclude_id: str | None = None) -> None:
    """An inbound number can only ring one trunk, or routing would be ambiguous."""
    rows = (await db.scalars(select(Trunk).where(Trunk.direction == TrunkDirection.INBOUND))).all()
    for t in rows:
        if t.id == exclude_id:
            continue
        if taken := sorted(set(numbers) & set(t.numbers or [])):
            raise HTTPException(status.HTTP_409_CONFLICT, f"{', '.join(taken)} already rings {t.name}")


async def _route(svc: Services, trunk: Trunk, agent_id: str | None) -> None:
    """Points the trunk's numbers at `agent_id` on Ulai (a dispatch rule), or stops routing them."""
    if agent_id and trunk.ulai_rule_id:
        await svc.gateway.update_rule(trunk.ulai_rule_id, agent_id)
    elif agent_id:
        rule = await svc.gateway.create_rule(f"studio · {trunk.name}", agent_id, trunk.ulai_trunk_id)
        trunk.ulai_rule_id = rule.id
    elif trunk.ulai_rule_id:
        await svc.gateway.delete_rule(trunk.ulai_rule_id)
        trunk.ulai_rule_id = None
    trunk.agent_id = agent_id


@router.get("", response_model=list[schemas.TrunkOut])
async def list_trunks(db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(Trunk).order_by(Trunk.created_at.desc()))).all()


@router.post("/inbound", response_model=schemas.TrunkOut, status_code=status.HTTP_201_CREATED)
async def create_inbound(
    body: schemas.InboundTrunkIn, db: AsyncSession = Depends(get_db), svc: Services = Depends(services)
):
    await _check_agent(db, body.agent_id)
    await _check_numbers_free(db, body.numbers)
    try:
        remote = await svc.gateway.create_inbound_trunk(body.name, body.numbers, body.allowed_addresses)
    except UlaiError as err:
        raise _bad_gateway(err) from err
    trunk = Trunk(
        name=body.name,
        direction=TrunkDirection.INBOUND,
        numbers=body.numbers,
        allowed_addresses=body.allowed_addresses,
        ulai_trunk_id=remote.id,
    )
    try:
        await _route(svc, trunk, body.agent_id)
    except UlaiError as err:
        await quietly(svc.gateway.delete_trunk("inbound", remote.id))
        raise _bad_gateway(err) from err
    db.add(trunk)
    await db.commit()
    svc.inbound.refresh()
    return await _get(db, trunk.id)


@router.post("/outbound", response_model=schemas.TrunkOut, status_code=status.HTTP_201_CREATED)
async def create_outbound(
    body: schemas.OutboundTrunkIn, db: AsyncSession = Depends(get_db), svc: Services = Depends(services)
):
    try:
        remote = await svc.gateway.create_outbound_trunk(
            body.name, body.address, body.transport, body.username, body.password
        )
    except UlaiError as err:
        raise _bad_gateway(err) from err
    trunk = Trunk(
        name=body.name,
        direction=TrunkDirection.OUTBOUND,
        numbers=body.numbers,
        address=body.address,
        transport=body.transport,
        username=body.username,
        ulai_trunk_id=remote.id,
    )
    db.add(trunk)
    await db.commit()
    return await _get(db, trunk.id)


@router.patch("/{trunk_id}", response_model=schemas.TrunkOut)
async def update_trunk(
    trunk_id: str,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    svc: Services = Depends(services),
):
    trunk = await _get(db, trunk_id)
    model = (
        schemas.InboundTrunkUpdate
        if trunk.direction == TrunkDirection.INBOUND
        else schemas.OutboundTrunkUpdate
    )
    try:
        body = model.model_validate(payload)
    except ValidationError as err:
        raise HTTPException(422, err.errors(include_url=False)) from err
    changes = body.model_dump(exclude_unset=True)

    try:
        if trunk.direction == TrunkDirection.INBOUND:
            if "numbers" in changes:
                await _check_numbers_free(db, changes["numbers"], exclude_id=trunk.id)
            if {"name", "numbers", "allowed_addresses"} & changes.keys():
                await svc.gateway.update_inbound_trunk(
                    trunk.ulai_trunk_id,
                    changes.get("name", trunk.name),
                    changes.get("numbers", trunk.numbers),
                    changes.get("allowed_addresses", trunk.allowed_addresses),
                )
            if "agent_id" in changes and changes["agent_id"] != trunk.agent_id:
                await _check_agent(db, changes["agent_id"])
                await _route(svc, trunk, changes["agent_id"])
        else:
            remote = {
                k: v
                for k, v in changes.items()
                if k in ("name", "address", "transport", "username", "password")
            }
            if remote.get("password") == "":
                remote.pop("password")
            if remote:
                await svc.gateway.update_outbound_trunk(trunk.ulai_trunk_id, **remote)
    except UlaiError as err:
        raise _bad_gateway(err) from err

    for key in ("name", "numbers", "allowed_addresses", "address", "transport", "username"):
        if key in changes:
            setattr(trunk, key, changes[key])
    await db.commit()
    svc.inbound.refresh()
    return await _get(db, trunk.id)


@router.put("/{trunk_id}/enabled", response_model=schemas.TrunkOut)
async def set_enabled(
    trunk_id: str,
    body: schemas.EnabledIn,
    db: AsyncSession = Depends(get_db),
    svc: Services = Depends(services),
):
    trunk = await _get(db, trunk_id)
    try:
        await svc.gateway.set_trunk_enabled(trunk.direction.value, trunk.ulai_trunk_id, body.enabled)
    except UlaiError as err:
        raise _bad_gateway(err) from err
    trunk.enabled = body.enabled
    await db.commit()
    svc.inbound.refresh()
    return await _get(db, trunk.id)


@router.delete("/{trunk_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trunk(trunk_id: str, db: AsyncSession = Depends(get_db), svc: Services = Depends(services)):
    trunk = await _get(db, trunk_id)
    try:
        if trunk.ulai_rule_id:
            await svc.gateway.delete_rule(trunk.ulai_rule_id)
        await svc.gateway.delete_trunk(trunk.direction.value, trunk.ulai_trunk_id)
    except UlaiError as err:
        raise _bad_gateway(err) from err
    await db.delete(trunk)
    await db.commit()
    svc.inbound.refresh()
