"""Telemetry: latest snapshot and historical series for charts."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..constants import METRICS
from ..schemas import LatestTelemetry, MetricPoint, MetricSeries
from ..services import telemetry as telemetry_svc
from .deps import get_session

router = APIRouter(prefix="/devices/{device_id}/telemetry", tags=["telemetry"])


@router.get("/latest", response_model=LatestTelemetry)
def latest(device_id: str, session: Session = Depends(get_session)):
    ts, metrics = telemetry_svc.get_latest(session, device_id)
    return LatestTelemetry(device_id=device_id, ts=ts, metrics=metrics)


@router.get("/history", response_model=list[MetricSeries])
def history(
    device_id: str,
    metric: str | None = Query(None, description="Одна метрика; если не задана — все"),
    start: datetime | None = None,
    end: datetime | None = None,
    max_points: int = Query(500, ge=10, le=5000),
    session: Session = Depends(get_session),
):
    wanted = [metric] if metric else list(METRICS)
    out: list[MetricSeries] = []
    for m in wanted:
        points = telemetry_svc.get_history(session, device_id, m, start, end, max_points)
        out.append(MetricSeries(
            metric=m,
            points=[MetricPoint(ts=ts, value=value) for ts, value in points],
        ))
    return out
