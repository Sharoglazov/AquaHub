"""ORM models for devices, telemetry, actuator state, thresholds, alerts,
schedules and push tokens."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # device_id
    name: Mapped[str] = mapped_column(String(128), default="")
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    thresholds: Mapped[list["Threshold"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class Telemetry(Base):
    """One measured value. Narrow schema keeps adding metrics trivial and makes
    per-metric history queries and downsampling straightforward."""

    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metric: Mapped[str] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        Index("ix_telemetry_device_metric_ts", "device_id", "metric", "ts"),
    )


class ActuatorState(Base):
    __tablename__ = "actuator_state"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actuator: Mapped[str] = mapped_column(String(32), primary_key=True)
    state_json: Mapped[str] = mapped_column(String(512), default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Threshold(Base):
    __tablename__ = "thresholds"
    __table_args__ = (UniqueConstraint("device_id", "metric", name="uq_threshold_device_metric"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    metric: Mapped[str] = mapped_column(String(32))
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    device: Mapped[Device] = relationship(back_populates="thresholds")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    metric: Mapped[str | None] = mapped_column(String(32), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="warning")  # info|warning|critical
    message: Mapped[str] = mapped_column(String(256))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeedingSchedule(Base):
    __tablename__ = "feeding_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    hour: Mapped[int] = mapped_column(Integer)      # 0..23 (local server time)
    minute: Mapped[int] = mapped_column(Integer)    # 0..59
    portions: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class LightScenario(Base):
    __tablename__ = "light_scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    on_hour: Mapped[int] = mapped_column(Integer)
    on_minute: Mapped[int] = mapped_column(Integer)
    off_hour: Mapped[int] = mapped_column(Integer)
    off_minute: Mapped[int] = mapped_column(Integer)
    brightness: Mapped[int] = mapped_column(Integer, default=80)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class PushToken(Base):
    __tablename__ = "push_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(512), unique=True)
    platform: Mapped[str] = mapped_column(String(16), default="android")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
