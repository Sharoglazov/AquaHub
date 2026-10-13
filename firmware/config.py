"""Configuration for the aquarium device agent (the emulated Raspberry Pi).

All settings are read from environment variables so the agent behaves the same
whether it runs locally or inside Docker. On real hardware only the sensor/actuator
backends change — this configuration layer stays identical.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


@dataclass
class DeviceConfig:
    device_id: str = os.environ.get("AQUA_DEVICE_ID", "tank-01")
    broker_host: str = os.environ.get("AQUA_BROKER_HOST", "localhost")
    broker_port: int = _env_int("AQUA_BROKER_PORT", 1883)
    username: str | None = os.environ.get("AQUA_BROKER_USER") or None
    password: str | None = os.environ.get("AQUA_BROKER_PASS") or None

    # How often telemetry is published, seconds.
    telemetry_interval_s: float = _env_float("AQUA_TELEMETRY_INTERVAL", 3.0)

    # Simulation speed multiplier: 1.0 = real time. Higher = faster physics
    # (useful to observe schedules/alerts quickly during a demo).
    time_scale: float = _env_float("AQUA_TIME_SCALE", 1.0)

    # Comma-separated fault-injection flags for demos / test report, e.g.
    # "heater_stuck_off,ato_off". See simulator.physics for supported faults.
    faults: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        raw = os.environ.get("AQUA_FAULTS", "")
        self.faults = {f.strip() for f in raw.split(",") if f.strip()}
