"""Telemetry storage and queries."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import DEFAULT_THRESHOLDS
from ..models import Device, Telemetry, Threshold


def ensure_device(session: Session, device_id: str, *, name: str = "") -> Device:
    """Return the device, creating it (with default thresholds) if unknown."""
    device = session.get(Device, device_id)
    if device is None:
        device = Device(id=device_id, name=name or device_id)
        session.add(device)
        for metric, (mn, mx, enabled) in DEFAULT_THRESHOLDS.items():
            session.add(Threshold(device_id=device_id, metric=metric,
                                  min_value=mn, max_value=mx, enabled=enabled))
        session.commit()
    return device


def store_sample(session: Session, device_id: str, ts: datetime,
                 metrics: dict[str, float]) -> None:
    ensure_device(session, device_id)
    for metric, value in metrics.items():
        if value is None:
            continue
        session.add(Telemetry(device_id=device_id, ts=ts, metric=metric, value=float(value)))
    device = session.get(Device, device_id)
    if device is not None:
        device.online = True
        device.last_seen = datetime.now(timezone.utc)
    session.commit()


def get_latest(session: Session, device_id: str) -> tuple[datetime | None, dict[str, float]]:
    """Most recent value of each metric for a device."""
    metrics: dict[str, float] = {}
    latest_ts: datetime | None = None
    rows = session.execute(
        select(Telemetry.metric, Telemetry.value, Telemetry.ts)
        .where(Telemetry.device_id == device_id)
        .order_by(Telemetry.ts.desc())
        .limit(200)
    ).all()
    for metric, value, ts in rows:
        if metric not in metrics:
            metrics[metric] = value
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
    return latest_ts, metrics


def get_history(session: Session, device_id: str, metric: str,
                start: datetime | None, end: datetime | None,
                max_points: int = 500) -> list[tuple[datetime, float]]:
    """Return (ts, value) points for a metric, averaged into at most
    ``max_points`` time buckets so charts stay light over long ranges."""
    stmt = select(Telemetry.ts, Telemetry.value).where(
        Telemetry.device_id == device_id, Telemetry.metric == metric
    )
    if start is not None:
        stmt = stmt.where(Telemetry.ts >= start)
    if end is not None:
        stmt = stmt.where(Telemetry.ts <= end)
    rows = session.execute(stmt.order_by(Telemetry.ts.asc())).all()
    points = [(ts, value) for ts, value in rows]
    if len(points) <= max_points:
        return points
    return _downsample(points, max_points)


def _downsample(points: list[tuple[datetime, float]], max_points: int) -> list[tuple[datetime, float]]:
    bucket = len(points) / max_points
    out: list[tuple[datetime, float]] = []
    i = 0.0
    idx = 0
    while idx < len(points):
        end = int(i + bucket)
        chunk = points[idx:max(end, idx + 1)]
        if not chunk:
            break
        avg = sum(v for _, v in chunk) / len(chunk)
        mid_ts = chunk[len(chunk) // 2][0]
        out.append((mid_ts, round(avg, 3)))
        idx = max(end, idx + 1)
        i += bucket
    return out
