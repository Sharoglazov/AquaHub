"""Per-device threshold configuration."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import METRICS
from ..models import Threshold
from ..schemas import ThresholdOut, ThresholdUpdate
from ..services import telemetry as telemetry_svc
from .deps import get_session, require_api_key

router = APIRouter(prefix="/devices/{device_id}/thresholds", tags=["thresholds"])


@router.get("", response_model=list[ThresholdOut])
def list_thresholds(device_id: str, session: Session = Depends(get_session)):
    telemetry_svc.ensure_device(session, device_id)
    return list(session.execute(
        select(Threshold).where(Threshold.device_id == device_id)
    ).scalars())


@router.put("/{metric}", response_model=ThresholdOut, dependencies=[Depends(require_api_key)])
def update_threshold(device_id: str, metric: str, body: ThresholdUpdate,
                     session: Session = Depends(get_session)):
    if metric not in METRICS:
        raise HTTPException(400, f"unknown metric '{metric}'")
    telemetry_svc.ensure_device(session, device_id)
    th = session.execute(
        select(Threshold).where(Threshold.device_id == device_id, Threshold.metric == metric)
    ).scalars().first()
    if th is None:
        th = Threshold(device_id=device_id, metric=metric)
        session.add(th)
    if body.min_value is not None:
        th.min_value = body.min_value
    if body.max_value is not None:
        th.max_value = body.max_value
    if body.enabled is not None:
        th.enabled = body.enabled
    session.commit()
    session.refresh(th)
    return th
