"""Devices and their current actuator state."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ActuatorState, Device
from ..schemas import ActuatorStateOut, DeviceCreate, DeviceOut
from ..services import telemetry as telemetry_svc
from .deps import get_session, require_api_key

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
def list_devices(session: Session = Depends(get_session)):
    return list(session.execute(select(Device).order_by(Device.id)).scalars())


@router.post("", response_model=DeviceOut, dependencies=[Depends(require_api_key)])
def create_device(body: DeviceCreate, session: Session = Depends(get_session)):
    return telemetry_svc.ensure_device(session, body.id, name=body.name)


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: str, session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "device not found")
    return device


@router.get("/{device_id}/actuators", response_model=list[ActuatorStateOut])
def get_actuators(device_id: str, session: Session = Depends(get_session)):
    rows = session.execute(
        select(ActuatorState).where(ActuatorState.device_id == device_id)
    ).scalars()
    return [
        ActuatorStateOut(actuator=r.actuator, state=json.loads(r.state_json),
                         updated_at=r.updated_at)
        for r in rows
    ]
