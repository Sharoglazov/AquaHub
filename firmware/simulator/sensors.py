"""Sensor readout layer.

Converts the tank's *true* physical state into *measured* values, adding
small per-sensor measurement noise. On real hardware this module would read an
I2C/analog sensor instead; the returned dict shape stays the same so the agent
and backend are unaffected.
"""
from __future__ import annotations

import random

from .physics import TankModel


def read_sensors(model: TankModel) -> dict[str, float]:
    """Return one telemetry sample (measured metrics) from the model."""
    return {
        "temperature_c": round(model.temperature_c + random.gauss(0.0, 0.05), 2),
        "ph": round(model.ph + random.gauss(0.0, 0.02), 2),
        "water_level_pct": round(model.water_level_pct + random.gauss(0.0, 0.2), 1),
        "illuminance_lux": round(max(0.0, model.illuminance_lux + random.gauss(0.0, 3.0)), 1),
        "tds_ppm": round(max(0.0, model.tds_ppm + random.gauss(0.0, 1.0)), 1),
    }
