"""Control service: turn REST commands into MQTT ``cmd/*`` publishes."""
from __future__ import annotations

import uuid

from .. import mqtt_client


def send_command(device_id: str, actuator: str, payload: dict) -> tuple[str, dict]:
    """Publish a command to the device. Returns (topic, published_payload)."""
    body = {k: v for k, v in payload.items() if v is not None}
    body.setdefault("cmd_id", f"c-{uuid.uuid4().hex[:8]}")
    topic = f"aquarium/{device_id}/cmd/{actuator}"
    mqtt_client.publish(topic, body, qos=1)
    return topic, body


def feed(device_id: str, portions: int) -> tuple[str, dict]:
    return send_command(device_id, "feeder", {"action": "feed", "portions": portions})
