"""Device agent — the MQTT-facing process of the emulated Raspberry Pi.

Owns a :class:`TankModel`, publishes telemetry and actuator state, and reacts to
commands from the backend. A lock guards the model because paho delivers
commands on its network thread while the main loop advances the physics.
"""
from __future__ import annotations

import json
import logging
import signal
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from config import DeviceConfig
from simulator.actuators import ACTUATORS, apply_command, build_state
from simulator.physics import TankModel
from simulator.sensors import read_sensors

log = logging.getLogger("device-agent")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DeviceAgent:
    def __init__(self, cfg: DeviceConfig) -> None:
        self.cfg = cfg
        self.model = TankModel(faults=cfg.faults)
        self._lock = threading.Lock()
        self._stop = threading.Event()

        self.base = f"aquarium/{cfg.device_id}"
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"agent-{cfg.device_id}",
        )
        if cfg.username:
            self.client.username_pw_set(cfg.username, cfg.password)
        self.client.will_set(
            f"{self.base}/status",
            json.dumps({"device_id": cfg.device_id, "status": "offline", "ts": _now_iso()}),
            qos=1,
            retain=True,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    # ----------------------------------------------------------------- callbacks
    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code != 0:
            log.error("connect failed: %s", reason_code)
            return
        log.info("connected to broker as %s", self.cfg.device_id)
        client.publish(
            f"{self.base}/status",
            json.dumps({"device_id": self.cfg.device_id, "status": "online", "ts": _now_iso()}),
            qos=1,
            retain=True,
        )
        client.subscribe(f"{self.base}/cmd/+", qos=1)
        with self._lock:
            for actuator in ACTUATORS:
                self._publish_state(actuator)

    def _on_message(self, client, userdata, msg) -> None:
        parts = msg.topic.split("/")
        # aquarium/{id}/cmd/{actuator}
        if len(parts) != 4 or parts[2] != "cmd":
            return
        actuator = parts[3]
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            log.warning("bad command payload on %s", msg.topic)
            return

        with self._lock:
            ok, err = apply_command(self.model, actuator, payload)
            if ok:
                self._publish_state(actuator)
        log.info("cmd %s %s -> ok=%s%s", actuator, payload, ok, f" ({err})" if err else "")

        cmd_id = payload.get("cmd_id")
        if cmd_id is not None:
            self.client.publish(
                f"{self.base}/cmd/{actuator}/ack",
                json.dumps({"cmd_id": cmd_id, "actuator": actuator, "ok": ok,
                            "error": err, "ts": _now_iso()}),
                qos=1,
            )

    # ------------------------------------------------------------------ publish
    def _publish_state(self, actuator: str) -> None:
        """Publish one retained actuator state. Caller must hold the lock."""
        self.client.publish(
            f"{self.base}/state/{actuator}",
            json.dumps(build_state(self.model, actuator)),
            qos=1,
            retain=True,
        )

    def _publish_telemetry(self) -> None:
        with self._lock:
            self.model.step(self.cfg.telemetry_interval_s * self.cfg.time_scale)
            metrics = read_sensors(self.model)
        payload = {"device_id": self.cfg.device_id, "ts": _now_iso(), "metrics": metrics}
        self.client.publish(f"{self.base}/telemetry", json.dumps(payload), qos=0)
        log.debug("telemetry %s", metrics)

    # --------------------------------------------------------------------- run
    def run(self) -> None:
        self.client.connect(self.cfg.broker_host, self.cfg.broker_port, keepalive=30)
        self.client.loop_start()
        try:
            while not self._stop.is_set():
                self._publish_telemetry()
                self._stop.wait(self.cfg.telemetry_interval_s)
        finally:
            self.client.publish(
                f"{self.base}/status",
                json.dumps({"device_id": self.cfg.device_id, "status": "offline",
                            "ts": _now_iso()}),
                qos=1,
                retain=True,
            )
            self.client.loop_stop()
            self.client.disconnect()
            log.info("agent stopped")

    def stop(self, *_: object) -> None:
        self._stop.set()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = DeviceConfig()
    log.info("starting device agent device_id=%s broker=%s:%s faults=%s time_scale=%s",
             cfg.device_id, cfg.broker_host, cfg.broker_port,
             sorted(cfg.faults) or "-", cfg.time_scale)
    agent = DeviceAgent(cfg)
    signal.signal(signal.SIGINT, agent.stop)
    signal.signal(signal.SIGTERM, agent.stop)
    agent.run()


if __name__ == "__main__":
    main()
