"""Physical model of the aquarium.

Holds the *true* physical state and the actuator state, and advances the
simulation one step at a time. Sensor readings (with measurement noise) are
derived from this true state in ``sensors.py``.

The model is intentionally simple but *coupled*: turning the heater or light on
raises temperature, feeding spikes pH/TDS, the filter clears TDS, and evaporation
lowers the water level unless the auto top-off (ATO) compensates. This coupling
is what makes manual control and schedules visibly affect the dashboard, and lets
the test report demonstrate real alert conditions via fault injection.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

AMBIENT_TEMP_C = 22.0
PH_BASELINE = 7.0
TDS_BASELINE = 160.0
MAX_LUX = 900.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class TankModel:
    """True physical + actuator state of one aquarium."""

    faults: set[str] = field(default_factory=set)

    # --- physical state ---
    temperature_c: float = 25.0
    ph: float = 7.1
    water_level_pct: float = 97.0
    illuminance_lux: float = 8.0
    tds_ppm: float = 165.0

    # --- actuator state ---
    light_on: bool = False
    light_brightness: int = 70          # 0..100
    filter_on: bool = True
    pump_on: bool = True
    pump_intensity: int = 55            # 0..100
    heater_on: bool = True
    heater_mode: str = "auto"           # "auto" | "manual"
    heater_target_c: float = 25.5
    feeder_last_fed: datetime | None = None
    feeder_portions_today: int = 0

    # --- internal ---
    _heater_heating: bool = False
    _last_reset_day: date = field(default_factory=lambda: datetime.now(timezone.utc).date())

    # ------------------------------------------------------------------ physics
    def step(self, dt_seconds: float) -> None:
        """Advance the physical state by ``dt_seconds`` of simulated time."""
        dt_min = dt_seconds / 60.0
        self._roll_over_day()

        self._step_temperature(dt_min)
        self._step_ph(dt_min)
        self._step_water_level(dt_min)
        self._step_tds(dt_min)
        self._step_light()

    def _step_temperature(self, dt_min: float) -> None:
        heating = self._heater_should_heat()
        self._heater_heating = heating
        heat_input = 0.0
        if heating and "heater_stuck_off" not in self.faults:
            heat_input = 0.6
        light_input = 0.05 * (self.light_brightness / 100.0) if self.light_on else 0.0
        cooling = 0.08 * (AMBIENT_TEMP_C - self.temperature_c)
        self.temperature_c += dt_min * (cooling + heat_input + light_input)
        self.temperature_c += random.gauss(0.0, 0.02)
        self.temperature_c = _clamp(self.temperature_c, 10.0, 40.0)

    def _step_ph(self, dt_min: float) -> None:
        target = 6.1 if "ph_drift" in self.faults else PH_BASELINE
        self.ph += dt_min * (0.02 * (target - self.ph))
        self.ph += random.gauss(0.0, 0.005)
        self.ph = _clamp(self.ph, 4.0, 9.5)

    def _step_water_level(self, dt_min: float) -> None:
        self.water_level_pct -= dt_min * 0.05  # evaporation
        if "ato_off" not in self.faults and self.water_level_pct < 92.0:
            self.water_level_pct += dt_min * 0.40  # auto top-off refill
        self.water_level_pct = _clamp(self.water_level_pct, 0.0, 100.0)

    def _step_tds(self, dt_min: float) -> None:
        k = 0.15 if self.filter_on else 0.03
        self.tds_ppm += dt_min * (-k * (self.tds_ppm - TDS_BASELINE))
        self.tds_ppm += random.gauss(0.0, 0.5)
        self.tds_ppm = _clamp(self.tds_ppm, 0.0, 1500.0)

    def _step_light(self) -> None:
        base = (self.light_brightness / 100.0) * MAX_LUX if self.light_on else 8.0
        self.illuminance_lux = _clamp(base + random.gauss(0.0, base * 0.02 + 1.0), 0.0, 2000.0)

    def _heater_should_heat(self) -> bool:
        if not self.heater_on:
            return False
        if self.heater_mode == "manual":
            return True
        # auto: hysteresis around target
        if self.temperature_c < self.heater_target_c - 0.15:
            return True
        if self.temperature_c > self.heater_target_c + 0.15:
            return False
        return self._heater_heating

    def _roll_over_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._last_reset_day:
            self.feeder_portions_today = 0
            self._last_reset_day = today

    # ------------------------------------------------------------------ actions
    def feed(self, portions: int) -> None:
        portions = max(1, min(int(portions), 10))
        self.feeder_last_fed = datetime.now(timezone.utc)
        self.feeder_portions_today += portions
        # Feeding acidifies slightly and raises dissolved solids.
        self.ph = _clamp(self.ph - 0.05 * portions, 4.0, 9.5)
        self.tds_ppm = _clamp(self.tds_ppm + 12.0 * portions, 0.0, 1500.0)
