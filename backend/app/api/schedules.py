"""Automation schedules: auto-feeding and light scenarios."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FeedingSchedule, LightScenario
from ..schemas import (
    FeedingScheduleIn,
    FeedingScheduleOut,
    LightScenarioIn,
    LightScenarioOut,
)
from ..services import scheduler
from ..services import telemetry as telemetry_svc
from .deps import get_session, require_api_key

router = APIRouter(prefix="/devices/{device_id}/schedules", tags=["schedules"])


# ---------------------------------------------------------------------- feeding
@router.get("/feeding", response_model=list[FeedingScheduleOut])
def list_feeding(device_id: str, session: Session = Depends(get_session)):
    return list(session.execute(
        select(FeedingSchedule).where(FeedingSchedule.device_id == device_id)
    ).scalars())


@router.post("/feeding", response_model=FeedingScheduleOut,
             dependencies=[Depends(require_api_key)])
def create_feeding(device_id: str, body: FeedingScheduleIn,
                   session: Session = Depends(get_session)):
    telemetry_svc.ensure_device(session, device_id)
    fs = FeedingSchedule(device_id=device_id, **body.model_dump())
    session.add(fs)
    session.commit()
    session.refresh(fs)
    scheduler.sync_all()
    return fs


@router.delete("/feeding/{schedule_id}", status_code=204,
               dependencies=[Depends(require_api_key)])
def delete_feeding(device_id: str, schedule_id: int, session: Session = Depends(get_session)):
    fs = session.get(FeedingSchedule, schedule_id)
    if fs is None or fs.device_id != device_id:
        raise HTTPException(404, "schedule not found")
    session.delete(fs)
    session.commit()
    scheduler.sync_all()


# ------------------------------------------------------------------------ light
@router.get("/light", response_model=list[LightScenarioOut])
def list_light(device_id: str, session: Session = Depends(get_session)):
    return list(session.execute(
        select(LightScenario).where(LightScenario.device_id == device_id)
    ).scalars())


@router.post("/light", response_model=LightScenarioOut,
             dependencies=[Depends(require_api_key)])
def create_light(device_id: str, body: LightScenarioIn,
                 session: Session = Depends(get_session)):
    telemetry_svc.ensure_device(session, device_id)
    ls = LightScenario(device_id=device_id, **body.model_dump())
    session.add(ls)
    session.commit()
    session.refresh(ls)
    scheduler.sync_all()
    return ls


@router.delete("/light/{scenario_id}", status_code=204,
               dependencies=[Depends(require_api_key)])
def delete_light(device_id: str, scenario_id: int, session: Session = Depends(get_session)):
    ls = session.get(LightScenario, scenario_id)
    if ls is None or ls.device_id != device_id:
        raise HTTPException(404, "scenario not found")
    session.delete(ls)
    session.commit()
    scheduler.sync_all()
