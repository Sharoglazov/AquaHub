"""MQTT ingest and command publisher.

Runs a paho client on a background network thread. Inbound device messages
(telemetry, status, actuator state, command acks) are routed to the storage,
alert and WebSocket layers; outbound commands are published via :func:`publish`.
Each handler uses its own DB session because it runs off the request path.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from . import db
from .config import settings
from .models import ActuatorState, Device
from .services import alerts as alerts_svc
from .services import telemetry as telemetry_svc
from .ws import hub

log = logging.getLogger("mqtt")

_client: mqtt.Client | None = None


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


# --------------------------------------------------------------------- handlers
def _handle_telemetry(payload: dict) -> None:
    device_id = payload.get("device_id")
    metrics = payload.get("metrics") or {}
    if not device_id or not isinstance(metrics, dict):
        return
    ts = _parse_ts(payload.get("ts"))
    with db.SessionLocal() as session:
        telemetry_svc.store_sample(session, device_id, ts, metrics)
        alerts_svc.evaluate(session, device_id, metrics)
    hub.publish("telemetry", {"device_id": device_id, "ts": ts.isoformat(), "metrics": metrics})


def _handle_status(device_id: str, payload: dict) -> None:
    status = payload.get("status")
    with db.SessionLocal() as session:
        device = telemetry_svc.ensure_device(session, device_id)
        device.online = status == "online"
        if status == "online":
            device.last_seen = datetime.now(timezone.utc)
            session.commit()
            alerts_svc.resolve_device_alert(session, device_id)
        else:
            session.commit()
            alerts_svc.raise_device_alert(session, device_id, "устройство offline")
    hub.publish("status", {"device_id": device_id, "status": status})


def _handle_state(device_id: str, actuator: str, payload: dict) -> None:
    with db.SessionLocal() as session:
        row = session.get(ActuatorState, (device_id, actuator))
        if row is None:
            row = ActuatorState(device_id=device_id, actuator=actuator)
            session.add(row)
        row.state_json = json.dumps(payload)
        row.updated_at = datetime.now(timezone.utc)
        session.commit()
    hub.publish("state", {"device_id": device_id, "actuator": actuator, "state": payload})


def _on_message(client, userdata, msg) -> None:
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        log.warning("bad payload on %s", msg.topic)
        return
    parts = msg.topic.split("/")
    if len(parts) < 3 or parts[0] != "aquarium":
        return
    device_id, kind = parts[1], parts[2]
    try:
        if kind == "telemetry":
            _handle_telemetry(payload)
        elif kind == "status":
            _handle_status(device_id, payload)
        elif kind == "state" and len(parts) == 4:
            _handle_state(device_id, parts[3], payload)
        elif kind == "cmd" and parts[-1] == "ack":
            log.info("ack from %s: %s", device_id, payload)
    except Exception:  # noqa: BLE001 — never let one bad message kill ingest
        log.exception("error handling %s", msg.topic)


def _on_connect(client, userdata, flags, reason_code, properties=None) -> None:
    if reason_code != 0:
        log.error("broker connect failed: %s", reason_code)
        return
    log.info("connected to broker %s:%s", settings.broker_host, settings.broker_port)
    client.subscribe([("aquarium/+/telemetry", 0), ("aquarium/+/status", 1),
                      ("aquarium/+/state/+", 1), ("aquarium/+/cmd/+/ack", 1)])


# ----------------------------------------------------------------------- public
def start() -> None:
    global _client
    _client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="aqua-backend")
    if settings.broker_user:
        _client.username_pw_set(settings.broker_user, settings.broker_pass)
    _client.on_connect = _on_connect
    _client.on_message = _on_message
    _client.reconnect_delay_set(min_delay=1, max_delay=30)
    try:
        _client.connect(settings.broker_host, settings.broker_port, keepalive=60)
        _client.loop_start()
    except OSError as exc:
        log.error("could not connect to broker (%s); will retry in background", exc)
        _client.loop_start()  # paho will keep retrying


def stop() -> None:
    global _client
    if _client is not None:
        _client.loop_stop()
        _client.disconnect()
        _client = None


def publish(topic: str, payload: dict, qos: int = 1) -> None:
    if _client is None:
        log.warning("publish skipped (no MQTT client): %s", topic)
        return
    _client.publish(topic, json.dumps(payload), qos=qos)
