"""Manual control endpoints — publish MQTT commands to actuators."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..schemas import (
    CommandResult,
    FeedCommand,
    FilterCommand,
    HeaterCommand,
    LightCommand,
    PumpCommand,
)
from ..services import control
from .deps import require_api_key

router = APIRouter(
    prefix="/devices/{device_id}/control",
    tags=["control"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/light", response_model=CommandResult)
def control_light(device_id: str, body: LightCommand):
    topic, payload = control.send_command(device_id, "light", body.model_dump())
    return CommandResult(ok=True, published_topic=topic, payload=payload)


@router.post("/filter", response_model=CommandResult)
def control_filter(device_id: str, body: FilterCommand):
    topic, payload = control.send_command(device_id, "filter", body.model_dump())
    return CommandResult(ok=True, published_topic=topic, payload=payload)


@router.post("/pump", response_model=CommandResult)
def control_pump(device_id: str, body: PumpCommand):
    topic, payload = control.send_command(device_id, "pump", body.model_dump())
    return CommandResult(ok=True, published_topic=topic, payload=payload)


@router.post("/heater", response_model=CommandResult)
def control_heater(device_id: str, body: HeaterCommand):
    topic, payload = control.send_command(device_id, "heater", body.model_dump())
    return CommandResult(ok=True, published_topic=topic, payload=payload)


@router.post("/feed", response_model=CommandResult)
def control_feed(device_id: str, body: FeedCommand):
    topic, payload = control.feed(device_id, body.portions)
    return CommandResult(ok=True, published_topic=topic, payload=payload)
