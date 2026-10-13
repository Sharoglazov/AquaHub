"""Tests for MQTT ingest handlers and the threshold/alert pipeline.

Handlers are invoked directly (no broker). The WebSocket hub and push provider
are stubbed so we can assert on what would be broadcast/pushed.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select


@pytest.fixture()
def stub_side_effects(monkeypatch):
    """Capture push + ws side effects across the alert/ingest modules."""
    pushes: list[tuple] = []
    ws_events: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        "app.services.notifications.provider.send",
        lambda tokens, title, body, data=None: pushes.append((title, body, data)),
    )
    # Both modules import `hub` by reference; patch the shared object's method.
    monkeypatch.setattr("app.ws.hub.publish",
                        lambda kind, data: ws_events.append((kind, data)))
    return pushes, ws_events


def _telemetry(device_id="tank-01", **metrics):
    return {"device_id": device_id, "ts": "2026-09-25T12:00:00Z", "metrics": metrics}


def test_telemetry_ingest_stores_samples(session_factory, stub_side_effects):
    from app import mqtt_client
    from app.models import Telemetry

    mqtt_client._handle_telemetry(_telemetry(temperature_c=25.0, ph=7.1))

    with session_factory() as s:
        rows = list(s.execute(select(Telemetry)).scalars())
    metrics = {r.metric for r in rows}
    assert {"temperature_c", "ph"} <= metrics


def test_breach_opens_alert_and_pushes(session_factory, stub_side_effects):
    from app import mqtt_client
    from app.models import Alert

    pushes, ws_events = stub_side_effects
    # temperature default max is 27.0 → 31.0 breaches.
    mqtt_client._handle_telemetry(_telemetry(temperature_c=31.0))

    with session_factory() as s:
        alerts = list(s.execute(select(Alert).where(Alert.active.is_(True))).scalars())
    assert len(alerts) == 1
    assert alerts[0].metric == "temperature_c"
    assert alerts[0].severity == "critical"
    assert len(pushes) == 1
    assert any(kind == "alert" for kind, _ in ws_events)


def test_alert_debounce_suppresses_repeat_push(session_factory, stub_side_effects, monkeypatch):
    from app import mqtt_client
    from app.services import alerts as alerts_svc

    alerts_svc._last_push.clear()
    pushes, _ = stub_side_effects

    for _ in range(4):
        mqtt_client._handle_telemetry(_telemetry(temperature_c=32.0))

    # Sustained breach → one alert row, one push (debounced), not four.
    assert len(pushes) == 1


def test_recovery_resolves_alert(session_factory, stub_side_effects):
    from app import mqtt_client
    from app.models import Alert
    from app.services import alerts as alerts_svc

    alerts_svc._last_push.clear()
    mqtt_client._handle_telemetry(_telemetry(temperature_c=31.0))
    mqtt_client._handle_telemetry(_telemetry(temperature_c=25.0))  # back to normal

    with session_factory() as s:
        active = list(s.execute(select(Alert).where(Alert.active.is_(True))).scalars())
        resolved = list(s.execute(select(Alert).where(Alert.active.is_(False))).scalars())
    assert active == []
    assert len(resolved) == 1
    assert resolved[0].resolved_at is not None


def test_status_offline_raises_device_alert(session_factory, stub_side_effects):
    from app import mqtt_client
    from app.models import Alert
    from app.services import alerts as alerts_svc

    alerts_svc._last_push.clear()
    mqtt_client._handle_status("tank-01", {"status": "offline"})

    with session_factory() as s:
        alerts = list(s.execute(
            select(Alert).where(Alert.metric.is_(None), Alert.active.is_(True))
        ).scalars())
    assert len(alerts) == 1
    assert "offline" in alerts[0].message


def test_status_online_resolves_device_alert(session_factory, stub_side_effects):
    from app import mqtt_client
    from app.models import Alert
    from app.services import alerts as alerts_svc

    alerts_svc._last_push.clear()
    mqtt_client._handle_status("tank-01", {"status": "offline"})
    mqtt_client._handle_status("tank-01", {"status": "online"})

    with session_factory() as s:
        active = list(s.execute(
            select(Alert).where(Alert.metric.is_(None), Alert.active.is_(True))
        ).scalars())
    assert active == []


def test_actuator_state_persisted(session_factory, stub_side_effects):
    from app import mqtt_client
    from app.models import ActuatorState

    mqtt_client._handle_state("tank-01", "light", {"power": "on", "brightness": 80})

    with session_factory() as s:
        row = s.get(ActuatorState, ("tank-01", "light"))
    assert row is not None
    assert '"brightness": 80' in row.state_json


def test_disabled_threshold_does_not_alert(session_factory, stub_side_effects):
    from app import mqtt_client
    from app.models import Alert, Threshold
    from app.services import telemetry as telemetry_svc

    with session_factory() as s:
        telemetry_svc.ensure_device(s, "tank-01")
        th = s.execute(
            select(Threshold).where(Threshold.device_id == "tank-01",
                                    Threshold.metric == "temperature_c")
        ).scalars().first()
        th.enabled = False
        s.commit()

    mqtt_client._handle_telemetry(_telemetry(temperature_c=40.0))

    with session_factory() as s:
        alerts = list(s.execute(select(Alert)).scalars())
    assert alerts == []
