"""Alert history and manual resolution."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Alert
from ..schemas import AlertOut
from .deps import get_session, require_api_key

router = APIRouter(prefix="/devices/{device_id}/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(
    device_id: str,
    active: bool | None = Query(None, description="Только активные/закрытые"),
    limit: int = Query(100, ge=1, le=1000),
    session: Session = Depends(get_session),
):
    stmt = select(Alert).where(Alert.device_id == device_id)
    if active is not None:
        stmt = stmt.where(Alert.active.is_(active))
    stmt = stmt.order_by(Alert.created_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars())


@router.post("/{alert_id}/resolve", response_model=AlertOut,
             dependencies=[Depends(require_api_key)])
def resolve_alert(device_id: str, alert_id: int, session: Session = Depends(get_session)):
    alert = session.get(Alert, alert_id)
    if alert is None or alert.device_id != device_id:
        raise HTTPException(404, "alert not found")
    alert.active = False
    alert.resolved_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(alert)
    return alert
