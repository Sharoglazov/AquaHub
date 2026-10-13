"""Shared constants: the metric set, default thresholds and actuator names."""
from __future__ import annotations

# Order also drives dashboard display order in the app.
METRICS: tuple[str, ...] = (
    "temperature_c",
    "ph",
    "water_level_pct",
    "illuminance_lux",
    "tds_ppm",
)

METRIC_LABELS: dict[str, str] = {
    "temperature_c": "Температура, °C",
    "ph": "Кислотность, pH",
    "water_level_pct": "Уровень воды, %",
    "illuminance_lux": "Освещённость, лк",
    "tds_ppm": "TDS, ppm",
}

# (min, max, enabled) — used to seed a new device's thresholds.
DEFAULT_THRESHOLDS: dict[str, tuple[float | None, float | None, bool]] = {
    "temperature_c": (24.0, 27.0, True),
    "ph": (6.5, 7.8, True),
    "water_level_pct": (80.0, 100.0, True),
    "illuminance_lux": (0.0, 2000.0, False),  # depends on the light scenario
    "tds_ppm": (100.0, 300.0, True),
}

ACTUATORS: tuple[str, ...] = ("light", "filter", "pump", "heater", "feeder")
