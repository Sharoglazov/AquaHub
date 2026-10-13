"""Tests for the device physics model (shared simulator logic).

The firmware package lives outside backend/, so it is imported by path.
These tests document and lock the coupled behaviour the demo relies on.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

FIRMWARE = Path(__file__).resolve().parents[2] / "firmware"
sys.path.insert(0, str(FIRMWARE))

from simulator.actuators import apply_command, build_state  # noqa: E402
from simulator.physics import TankModel  # noqa: E402
from simulator.sensors import read_sensors  # noqa: E402


def test_heater_auto_raises_temperature_towards_target():
    m = TankModel(temperature_c=20.0, heater_on=True, heater_mode="auto", heater_target_c=26.0)
    for _ in range(200):
        m.step(10.0)  # 10 s steps
    assert m.temperature_c > 24.0


def test_heater_stuck_off_fault_prevents_heating():
    m = TankModel(temperature_c=20.0, heater_on=True, heater_mode="auto",
                  heater_target_c=26.0, faults={"heater_stuck_off"})
    start = m.temperature_c
    for _ in range(200):
        m.step(10.0)
    # With no heat input the tank drifts toward ambient (22°C), never to target.
    assert m.temperature_c < 23.0
    assert m.temperature_c <= start + 2.5


def test_feeding_raises_tds_and_lowers_ph():
    m = TankModel(ph=7.2, tds_ppm=160.0)
    ph_before, tds_before = m.ph, m.tds_ppm
    m.feed(3)
    assert m.tds_ppm > tds_before
    assert m.ph < ph_before
    assert m.feeder_portions_today == 3


def test_filter_off_keeps_tds_elevated_longer():
    fed_on = TankModel(tds_ppm=160.0, filter_on=True)
    fed_off = TankModel(tds_ppm=160.0, filter_on=False)
    fed_on.feed(5)
    fed_off.feed(5)
    for _ in range(60):
        fed_on.step(10.0)
        fed_off.step(10.0)
    # Filter clears dissolved solids faster than no filtration.
    assert fed_on.tds_ppm < fed_off.tds_ppm


def test_light_command_changes_illuminance():
    m = TankModel(light_on=False)
    m.step(1.0)
    dark = m.illuminance_lux
    apply_command(m, "light", {"power": "on", "brightness": 100})
    m.step(1.0)
    assert m.illuminance_lux > dark + 100


def test_light_brightness_clamped():
    m = TankModel()
    apply_command(m, "light", {"power": "on", "brightness": 999})
    assert m.light_brightness == 100
    apply_command(m, "light", {"brightness": -50})
    assert m.light_brightness == 0


def test_apply_command_unknown_actuator():
    m = TankModel()
    ok, err = apply_command(m, "laser", {"power": "on"})
    assert ok is False
    assert err is not None


def test_feeder_requires_feed_action():
    m = TankModel()
    ok, err = apply_command(m, "feeder", {"portions": 2})
    assert ok is False


def test_build_state_shapes():
    m = TankModel()
    light = build_state(m, "light")
    assert set(light) >= {"power", "brightness", "ts"}
    heater = build_state(m, "heater")
    assert heater["mode"] in ("auto", "manual")


def test_read_sensors_returns_all_metrics():
    m = TankModel()
    sample = read_sensors(m)
    assert set(sample) == {
        "temperature_c", "ph", "water_level_pct", "illuminance_lux", "tds_ppm"
    }
    assert all(isinstance(v, float) for v in sample.values())


def test_water_level_auto_topoff_recovers():
    m = TankModel(water_level_pct=85.0)
    for _ in range(120):
        m.step(10.0)
    assert m.water_level_pct > 88.0


def test_ato_off_fault_lets_level_fall():
    m = TankModel(water_level_pct=90.0, faults={"ato_off"})
    for _ in range(300):
        m.step(10.0)
    assert m.water_level_pct < 90.0
