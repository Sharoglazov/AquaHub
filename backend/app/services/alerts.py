"""Threshold evaluation, alert lifecycle and push dispatch.

Called from the MQTT ingest thread after each telemetry sample is stored. Keeps
a per-(device, metric) debounce so a sustained breach does not spam push
notifications, while still keeping the alert record active.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Alert, PushToken, Threshold
from ..ws import hub
from . import notifications

log = logging.getLogger("alerts")

_CRITICAL_METRICS = {"temperature_c", "water_level_pct"}
# module-level debounce: (device_id, key) -> monotonic seconds of last push
_last_push: dict[tuple[str, str], float] = {}


def _severity_for(metric: str | None) -> str:
    if metric is None or metric in _CRITICAL_METRICS:
        return "critical"
    return "warning"


def _should_push(device_id: str, key: str) -> bool:
    now = time.monotonic()
    last = _last_push.get((device_id, key))
    if last is None or (now - last) >= settings.alert_debounce_s:
        _last_push[(device_id, key)] = now
        return True
    return False


def _push(session: Session, title: str, body: str, data: dict) -> None:
    tokens = list(session.execute(select(PushToken.token)).scalars())
    notifications.provider.send(tokens, title, body, data)


def _active_alert(session: Session, device_id: str, metric: str | None) -> Alert | None:
    return session.execute(
        select(Alert).where(
            Alert.device_id == device_id, Alert.metric == metric, Alert.active.is_(True)
        )
    ).scalars().first()


def evaluate(session: Session, device_id: str, metrics: dict[str, float]) -> list[Alert]:
    """Check a telemetry sample against thresholds; open/resolve alerts."""
    thresholds = {
        t.metric: t
        for t in session.execute(
            select(Threshold).where(Threshold.device_id == device_id, Threshold.enabled.is_(True))
        ).scalars()
    }
    opened: list[Alert] = []

    for metric, value in metrics.items():
        th: Threshold | None = thresholds.get(metric)
        if th is None:
            continue
        breached = (th.min_value is not None and value < th.min_value) or (
            th.max_value is not None and value > th.max_value
        )
        if breached:
            opened_alert = _open_or_update(session, device_id, metric, value, th)
            if opened_alert is not None:
                opened.append(opened_alert)
        else:
            _resolve(session, device_id, metric)

    session.commit()
    return opened


def _open_or_update(session: Session, device_id: str, metric: str, value: float,
                    th: Threshold) -> Alert | None:
    existing = _active_alert(session, device_id, metric)
    bound = "ниже" if (th.min_value is not None and value < th.min_value) else "выше"
    limit = th.min_value if bound == "ниже" else th.max_value
    message = f"{metric}={value} {bound} порога {limit}"
    severity = _severity_for(metric)

    if existing is None:
        alert = Alert(device_id=device_id, metric=metric, severity=severity, message=message,
                      value=value, threshold_min=th.min_value, threshold_max=th.max_value,
                      active=True)
        session.add(alert)
        session.flush()
    else:
        existing.value = value
        existing.message = message
        alert = existing

    if _should_push(device_id, metric):
        _push(session, f"⚠ {device_id}: {metric}", message,
              {"device_id": device_id, "metric": metric, "value": str(value),
               "severity": severity})
        hub.publish("alert", {"device_id": device_id, "metric": metric,
                              "message": message, "severity": severity, "active": True})
        log.warning("ALERT %s %s: %s", device_id, metric, message)
    return alert if existing is None else None


def _resolve(session: Session, device_id: str, metric: str) -> None:
    existing = _active_alert(session, device_id, metric)
    if existing is None:
        return
    from datetime import datetime, timezone

    existing.active = False
    existing.resolved_at = datetime.now(timezone.utc)
    _last_push.pop((device_id, metric), None)
    hub.publish("alert", {"device_id": device_id, "metric": metric,
                          "message": "параметр вернулся в норму", "active": False})
    log.info("RESOLVED %s %s", device_id, metric)


def raise_device_alert(session: Session, device_id: str, message: str,
                       severity: str = "critical", key: str = "device") -> None:
    """Open a non-metric alert (e.g. device offline) with debounced push."""
    existing = _active_alert(session, device_id, None)
    if existing is None:
        session.add(Alert(device_id=device_id, metric=None, severity=severity,
                          message=message, active=True))
    session.commit()
    if _should_push(device_id, key):
        _push(session, f"⚠ {device_id}", message,
              {"device_id": device_id, "severity": severity})
        hub.publish("alert", {"device_id": device_id, "metric": None,
                              "message": message, "severity": severity, "active": True})
        log.warning("DEVICE ALERT %s: %s", device_id, message)


def resolve_device_alert(session: Session, device_id: str, key: str = "device") -> None:
    _resolve_nonmetric(session, device_id)
    _last_push.pop((device_id, key), None)


def _resolve_nonmetric(session: Session, device_id: str) -> None:
    existing = _active_alert(session, device_id, None)
    if existing is None:
        return
    from datetime import datetime, timezone

    existing.active = False
    existing.resolved_at = datetime.now(timezone.utc)
    session.commit()
    hub.publish("alert", {"device_id": device_id, "metric": None,
                          "message": "устройство снова на связи", "active": False})
