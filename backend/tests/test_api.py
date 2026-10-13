"""API-level tests: devices, telemetry, control, thresholds, schedules, push."""
from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_and_get_device(client):
    r = client.post("/devices", json={"id": "tank-01", "name": "Гостиная"})
    assert r.status_code == 200
    assert r.json()["id"] == "tank-01"

    r = client.get("/devices/tank-01")
    assert r.status_code == 200
    assert r.json()["name"] == "Гостиная"


def test_get_missing_device_404(client):
    assert client.get("/devices/nope").status_code == 404


def test_new_device_seeds_default_thresholds(client):
    client.post("/devices", json={"id": "tank-01"})
    r = client.get("/devices/tank-01/thresholds")
    assert r.status_code == 200
    metrics = {t["metric"] for t in r.json()}
    assert {"temperature_c", "ph", "water_level_pct", "tds_ppm"} <= metrics


def test_update_threshold(client):
    client.post("/devices", json={"id": "tank-01"})
    r = client.put("/devices/tank-01/thresholds/temperature_c",
                   json={"min_value": 23.0, "max_value": 28.0, "enabled": True})
    assert r.status_code == 200
    body = r.json()
    assert body["min_value"] == 23.0 and body["max_value"] == 28.0


def test_update_unknown_metric_400(client):
    client.post("/devices", json={"id": "tank-01"})
    assert client.put("/devices/tank-01/thresholds/salinity", json={"min_value": 1}).status_code == 400


def test_control_light_publishes_command(client, published):
    r = client.post("/devices/tank-01/control/light", json={"power": "on", "brightness": 60})
    assert r.status_code == 200
    topic, payload, _ = published[-1]
    assert topic == "aquarium/tank-01/cmd/light"
    assert payload["power"] == "on" and payload["brightness"] == 60
    assert "cmd_id" in payload


def test_control_feed_publishes_feed_action(client, published):
    r = client.post("/devices/tank-01/control/feed", json={"portions": 2})
    assert r.status_code == 200
    topic, payload, _ = published[-1]
    assert topic == "aquarium/tank-01/cmd/feeder"
    assert payload["action"] == "feed" and payload["portions"] == 2


def test_control_validation_rejects_bad_brightness(client):
    r = client.post("/devices/tank-01/control/light", json={"brightness": 500})
    assert r.status_code == 422


def test_pump_intensity_validation(client):
    assert client.post("/devices/tank-01/control/pump",
                       json={"power": "on", "intensity": -5}).status_code == 422


def test_feeding_schedule_crud(client):
    client.post("/devices", json={"id": "tank-01"})
    r = client.post("/devices/tank-01/schedules/feeding",
                    json={"hour": 8, "minute": 30, "portions": 2, "enabled": True})
    assert r.status_code == 200
    sid = r.json()["id"]

    r = client.get("/devices/tank-01/schedules/feeding")
    assert len(r.json()) == 1

    assert client.delete(f"/devices/tank-01/schedules/feeding/{sid}").status_code == 204
    assert client.get("/devices/tank-01/schedules/feeding").json() == []


def test_light_scenario_crud(client):
    client.post("/devices", json={"id": "tank-01"})
    r = client.post("/devices/tank-01/schedules/light",
                    json={"on_hour": 9, "on_minute": 0, "off_hour": 21, "off_minute": 0,
                          "brightness": 75})
    assert r.status_code == 200
    assert r.json()["brightness"] == 75


def test_register_push_token(client):
    r = client.post("/push/tokens", json={"token": "abc123", "platform": "android"})
    assert r.status_code == 201
    # idempotent
    assert client.post("/push/tokens", json={"token": "abc123"}).status_code == 201


def test_telemetry_latest_empty(client):
    r = client.get("/devices/tank-01/telemetry/latest")
    assert r.status_code == 200
    assert r.json()["metrics"] == {}
