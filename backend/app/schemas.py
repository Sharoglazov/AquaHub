"""Pydantic request/response schemas for the REST API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------- devices
class DeviceOut(BaseModel):
    id: str
    name: str
    online: bool
    last_seen: datetime | None

    class Config:
        from_attributes = True


class DeviceCreate(BaseModel):
    id: str = Field(..., examples=["tank-01"])
    name: str = ""


# ------------------------------------------------------------------- telemetry
class MetricPoint(BaseModel):
    ts: datetime
    value: float


class MetricSeries(BaseModel):
    metric: str
    points: list[MetricPoint]


class LatestTelemetry(BaseModel):
    device_id: str
    ts: datetime | None
    metrics: dict[str, float]


# -------------------------------------------------------------------- controls
class LightCommand(BaseModel):
    power: Literal["on", "off"] | None = None
    brightness: int | None = Field(None, ge=0, le=100)


class FilterCommand(BaseModel):
    power: Literal["on", "off"]


class PumpCommand(BaseModel):
    power: Literal["on", "off"] | None = None
    intensity: int | None = Field(None, ge=0, le=100)


class HeaterCommand(BaseModel):
    power: Literal["on", "off"] | None = None
    mode: Literal["auto", "manual"] | None = None
    target_c: float | None = Field(None, ge=15.0, le=32.0)


class FeedCommand(BaseModel):
    portions: int = Field(1, ge=1, le=10)


class CommandResult(BaseModel):
    ok: bool
    published_topic: str
    payload: dict[str, Any]


class ActuatorStateOut(BaseModel):
    actuator: str
    state: dict[str, Any]
    updated_at: datetime | None


# ------------------------------------------------------------------ thresholds
class ThresholdOut(BaseModel):
    metric: str
    min_value: float | None
    max_value: float | None
    enabled: bool

    class Config:
        from_attributes = True


class ThresholdUpdate(BaseModel):
    min_value: float | None = None
    max_value: float | None = None
    enabled: bool | None = None


# ---------------------------------------------------------------------- alerts
class AlertOut(BaseModel):
    id: int
    device_id: str
    metric: str | None
    severity: str
    message: str
    value: float | None
    threshold_min: float | None
    threshold_max: float | None
    active: bool
    created_at: datetime
    resolved_at: datetime | None

    class Config:
        from_attributes = True


# ------------------------------------------------------------------- schedules
class FeedingScheduleIn(BaseModel):
    hour: int = Field(..., ge=0, le=23)
    minute: int = Field(..., ge=0, le=59)
    portions: int = Field(1, ge=1, le=10)
    enabled: bool = True


class FeedingScheduleOut(FeedingScheduleIn):
    id: int
    device_id: str

    class Config:
        from_attributes = True


class LightScenarioIn(BaseModel):
    on_hour: int = Field(..., ge=0, le=23)
    on_minute: int = Field(..., ge=0, le=59)
    off_hour: int = Field(..., ge=0, le=23)
    off_minute: int = Field(..., ge=0, le=59)
    brightness: int = Field(80, ge=0, le=100)
    enabled: bool = True


class LightScenarioOut(LightScenarioIn):
    id: int
    device_id: str

    class Config:
        from_attributes = True


# ------------------------------------------------------------------ push token
class PushTokenIn(BaseModel):
    token: str
    platform: Literal["android", "ios", "web"] = "android"
