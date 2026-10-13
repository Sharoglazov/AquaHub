"""End-to-end integration check (no test framework, real broker).

Assumes an MQTT broker on localhost:1883. Starts the backend in-process and the
device agent in a thread, then verifies over the live system:

  1. the device connects and telemetry reaches the REST API,
  2. actuator state is reported and stored,
  3. a manual control command is delivered to the device (feeder portions rise),
  4. a threshold breach opens an alert and a push is dispatched.

Run:  python scripts/e2e_check.py
Exits non-zero on the first failed assertion.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "firmware"))

# Isolated DB + fast telemetry, console push. Set before importing app/config.
os.environ.setdefault("AQUA_DATABASE_URL", "sqlite:///./e2e.db")
os.environ.setdefault("AQUA_BROKER_HOST", "localhost")
os.environ.setdefault("AQUA_ALERT_DEBOUNCE_S", "1")

DB_PATH = ROOT / "e2e.db"
if DB_PATH.exists():
    DB_PATH.unlink()

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402

PASSED = 0


def check(label: str, cond: bool) -> None:
    global PASSED
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {label}")
    if not cond:
        print("\nE2E CHECK FAILED")
        os._exit(1)
    PASSED += 1


def wait_for(fn, timeout=25.0, interval=0.5):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    return last


def main() -> None:
    import httpx

    # --- start backend (real MQTT ingest connects to the broker) ---
    config = uvicorn.Config(app, host="127.0.0.1", port=8010, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    base = "http://127.0.0.1:8010"
    ready = wait_for(lambda: _health(base), timeout=20)
    check("backend /health responds", bool(ready))

    # --- start the device agent against the same broker ---
    from config import DeviceConfig
    from agent import DeviceAgent

    cfg = DeviceConfig()
    cfg.device_id = "tank-e2e"
    cfg.telemetry_interval_s = 1.0
    cfg.time_scale = 30.0  # speed up physics so schedules/heater move fast
    agent = DeviceAgent(cfg)
    at = threading.Thread(target=agent.run, daemon=True)
    at.start()

    with httpx.Client(base_url=base, timeout=5.0) as c:
        # 1. telemetry reaches the API
        latest = wait_for(lambda: _latest_has_metrics(c), timeout=25)
        check("telemetry flows device -> broker -> backend -> REST", bool(latest))

        # device shows online
        online = wait_for(lambda: c.get("/devices/tank-e2e").json().get("online") is True)
        check("device reported online", bool(online))

        # 2. actuator state reported + stored
        acts = wait_for(lambda: _actuators(c), timeout=15)
        check("actuator state stored (>=1 actuator)", bool(acts) and len(acts) >= 1)

        # 3. control command delivered to device: feed and observe portions rise
        before = _feeder_portions(c)
        r = c.post("/devices/tank-e2e/control/feed", json={"portions": 3})
        check("feed command accepted (HTTP 200)", r.status_code == 200)
        rose = wait_for(lambda: _feeder_portions(c) is not None
                        and _feeder_portions(c) >= (before or 0) + 3, timeout=15)
        check("feeder portions increased after command (round-trip)", bool(rose))

        # light control round-trips into state
        c.post("/devices/tank-e2e/control/light", json={"power": "on", "brightness": 90})
        lit = wait_for(lambda: _light_on(c), timeout=15)
        check("light command reflected in actuator state", bool(lit))

        # 4. threshold breach -> alert. Tighten temp max so current temp breaches.
        c.put("/devices/tank-e2e/thresholds/temperature_c",
              json={"min_value": 0.0, "max_value": 5.0, "enabled": True})
        alert = wait_for(lambda: _active_alert(c, "temperature_c"), timeout=20)
        check("threshold breach opened an active alert", bool(alert))

        # recovery: widen threshold -> alert resolves
        c.put("/devices/tank-e2e/thresholds/temperature_c",
              json={"min_value": 0.0, "max_value": 99.0, "enabled": True})
        resolved = wait_for(lambda: not _active_alert(c, "temperature_c"), timeout=20)
        check("alert resolves when value back in range", bool(resolved))

    agent.stop()
    print(f"\nALL {PASSED} E2E CHECKS PASSED")


# --- helpers ---
def _health(base):
    try:
        import httpx
        return httpx.get(f"{base}/health", timeout=2).status_code == 200
    except Exception:
        return False


def _latest_has_metrics(c):
    try:
        m = c.get("/devices/tank-e2e/telemetry/latest").json().get("metrics", {})
        return m if m else None
    except Exception:
        return None


def _actuators(c):
    try:
        a = c.get("/devices/tank-e2e/actuators").json()
        return a if a else None
    except Exception:
        return None


def _feeder_portions(c):
    for a in (_actuators(c) or []):
        if a["actuator"] == "feeder":
            return a["state"].get("portions_today")
    return None


def _light_on(c):
    for a in (_actuators(c) or []):
        if a["actuator"] == "light":
            return a["state"].get("power") == "on"
    return False


def _active_alert(c, metric):
    try:
        alerts = c.get("/devices/tank-e2e/alerts", params={"active": True}).json()
        return any(al["metric"] == metric for al in alerts)
    except Exception:
        return False


if __name__ == "__main__":
    main()
