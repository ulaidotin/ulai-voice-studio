from datetime import UTC, datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import catalog, schemas
from ..auth import require_admin
from ..config import Settings, get_settings
from ..db import get_db
from ..deps import Services, services
from ..models import ACTIVE_CALL_STATUSES, Agent, Call, CallDirection, Trunk
from ..ulai.gateway import UlaiError
from ..ulai.profile import BUILTIN_VARIABLES

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])


@router.get("/overview", response_model=schemas.Overview)
async def overview(db: AsyncSession = Depends(get_db)):
    now = datetime.now(UTC)
    today = datetime.combine(now.date(), time.min, tzinfo=UTC)
    week_start = today - timedelta(days=6)

    week = (await db.scalars(select(Call).where(Call.created_at >= week_start))).all()

    def aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

    days = {
        (week_start + timedelta(days=i)).date().isoformat(): {d.value: 0 for d in CallDirection}
        for i in range(7)
    }
    for c in week:
        key = aware(c.created_at).date().isoformat()
        if key in days:
            days[key][c.direction.value] += 1

    phone_out = [c for c in week if c.direction == CallDirection.OUTBOUND and c.status.is_final]
    answered = [c for c in phone_out if c.answered_at is not None]
    finished = [c for c in week if c.duration_seconds]

    recent = (await db.scalars(select(Call).order_by(Call.created_at.desc()).limit(8))).all()
    return schemas.Overview(
        active_calls=await db.scalar(
            select(func.count()).select_from(Call).where(Call.status.in_(ACTIVE_CALL_STATUSES))
        )
        or 0,
        calls_today=sum(1 for c in week if aware(c.created_at) >= today),
        calls_7d=len(week),
        answer_rate_7d=(len(answered) / len(phone_out)) if phone_out else None,
        avg_duration_7d=(sum(c.duration_seconds for c in finished) / len(finished)) if finished else None,
        total_minutes_7d=round(sum(c.duration_seconds or 0 for c in week) / 60, 1),
        daily=[schemas.DailyCount(date=d, **counts) for d, counts in days.items()],
        recent=list(recent),
        agents=await db.scalar(select(func.count()).select_from(Agent)) or 0,
        trunks=await db.scalar(select(func.count()).select_from(Trunk)) or 0,
    )


@router.get("/catalog", response_model=schemas.Catalog)
async def get_catalog():
    return schemas.Catalog(
        models=catalog.MODELS,
        voices=catalog.VOICES,
        languages=catalog.LANGUAGES,
        builtin_variables=BUILTIN_VARIABLES,
    )


@router.get("/health", response_model=schemas.HealthOut)
async def health(svc: Services = Depends(services), settings: Settings = Depends(get_settings)):
    if not settings.ulai_api_key.get_secret_value():
        ulai, detail, project = "unconfigured", "ULAI_API_KEY is not set", None
    else:
        try:
            project = await svc.gateway.check()
            ulai, detail = "ok", ""
        except UlaiError as err:
            ulai, detail, project = "error", str(err), None
    return schemas.HealthOut(
        ulai=ulai,
        ulai_detail=detail,
        project_id=project,
        google_credentials=bool(settings.google_credentials_json),
        inbound_listener=svc.inbound.state,
    )
