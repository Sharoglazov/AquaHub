"""Actuator layer: apply incoming commands to the model and report state.

Translates MQTT command payloads (see ``docs/mqtt-contract.md``) into changes on
the :class:`~simulator.physics.TankModel`, and builds the retained ``state/*``
payloads the agent publishes back.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .physics import TankModel

ACTUATORS = ("light", "filter", "pump", "heater", "feeder")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_bool_power(payload: dict) -> bool | None:
    power = payload.get("power")
    if isinstance(power, str):
        return power.lower() == "on"
    if isinstance(power, bool):
        return power
    return None


def apply_command(model: TankModel, actuator: str, payload: dict) -> tuple[bool, str | None]:
    """Apply a command. Returns ``(ok, error_message)``."""
    if actuator not in ACTUATORS:
        return False, f"unknown actuator '{actuator}'"

    try:
        if actuator == "light":
            power = _as_bool_power(payload)
            if power is not None:
                model.light_on = power
            if "brightness" in payload:
                model.light_brightness = int(max(0, min(100, payload["brightness"])))
        elif actuator == "filter":
            power = _as_bool_power(payload)
            if power is not None:
                model.filter_on = power
        elif actuator == "pump":
            power = _as_bool_power(payload)
            if power is not None:
                model.pump_on = power
            if "intensity" in payload:
                model.pump_intensity = int(max(0, min(100, payload["intensity"])))
        elif actuator == "heater":
            power = _as_bool_power(payload)
            if power is not None:
                model.heater_on = power
            if payload.get("mode") in ("auto", "manual"):
                model.heater_mode = payload["mode"]
            if "target_c" in payload:
                model.heater_target_c = float(max(15.0, min(32.0, payload["target_c"])))
        elif actuator == "feeder":
            if payload.get("action") == "feed":
                model.feed(int(payload.get("portions", 1)))
            else:
                return False, "feeder expects action='feed'"
    except (TypeError, ValueError) as exc:
        return False, f"invalid payload: {exc}"

    return True, None


def build_state(model: TankModel, actuator: str) -> dict:
    """Build the retained ``state/{actuator}`` payload for one actuator."""
    ts = _now_iso()
    if actuator == "light":
        return {"power": "on" if model.light_on else "off",
                "brightness": model.light_brightness, "ts": ts}
    if actuator == "filter":
        return {"power": "on" if model.filter_on else "off", "ts": ts}
    if actuator == "pump":
        return {"power": "on" if model.pump_on else "off",
                "intensity": model.pump_intensity, "ts": ts}
    if actuator == "heater":
        return {"power": "on" if model.heater_on else "off", "mode": model.heater_mode,
                "target_c": round(model.heater_target_c, 2),
                "heating": model._heater_heating, "ts": ts}
    if actuator == "feeder":
        return {"last_fed": model.feeder_last_fed.strftime("%Y-%m-%dT%H:%M:%SZ")
                if model.feeder_last_fed else None,
                "portions_today": model.feeder_portions_today, "ts": ts}
    raise ValueError(f"unknown actuator '{actuator}'")
