# Контракт MQTT

Единый контракт обмена между устройством («Raspberry Pi», эмулируется) и backend.
Именно он позволяет заменить симулятор на реальное железо без изменений на сервере.

- **Брокер:** Mosquitto, порт `1883` (TCP), `9001` (WebSocket).
- **QoS:** телеметрия — QoS 0 (частая, потеря единичного пакета некритична);
  команды и состояния — QoS 1.
- **Формат:** UTF-8 JSON.
- **Идентификатор устройства:** `device_id`, напр. `tank-01`. Один агент = один аквариум.
- **Время:** ISO-8601 UTC, суффикс `Z`, напр. `2026-09-25T12:00:00Z`.

## Дерево топиков

```
aquarium/{device_id}/telemetry              device → server   телеметрия датчиков
aquarium/{device_id}/status                 device → server   online/offline (retained, LWT)
aquarium/{device_id}/state/{actuator}       device → server   текущее состояние устройства (retained)
aquarium/{device_id}/cmd/{actuator}         server → device   команда управления
aquarium/{device_id}/cmd/{actuator}/ack     device → server   подтверждение выполнения
```

`{actuator}` ∈ `light | filter | pump | heater | feeder`.

## Сообщения device → server

### `telemetry`
```json
{
  "device_id": "tank-01",
  "ts": "2026-09-25T12:00:00Z",
  "metrics": {
    "temperature_c": 25.3,
    "ph": 7.12,
    "water_level_pct": 96.2,
    "illuminance_lux": 320.0,
    "tds_ppm": 180.0
  }
}
```
Любая метрика может отсутствовать (датчик недоступен) — backend сохранит присутствующие.

### `status` (retained, также Last Will)
```json
{ "device_id": "tank-01", "status": "online", "ts": "2026-09-25T12:00:00Z" }
```
LWT публикует `{"status":"offline"}` при обрыве соединения.

### `state/{actuator}` (retained)
Полное текущее состояние устройства. Примеры:
```json
// state/light
{ "power": "on", "brightness": 80, "ts": "..." }
// state/filter
{ "power": "on", "ts": "..." }
// state/pump
{ "power": "on", "intensity": 60, "ts": "..." }
// state/heater
{ "power": "on", "mode": "auto", "target_c": 25.5, "ts": "..." }
// state/feeder
{ "last_fed": "2026-09-25T08:00:00Z", "portions_today": 2, "ts": "..." }
```

### `cmd/{actuator}/ack`
```json
{ "cmd_id": "c-8f3a", "actuator": "feeder", "ok": true, "ts": "..." }
```

## Сообщения server → device

### `cmd/{actuator}`
Общая обёртка: `cmd_id` — необязательный идентификатор для сопоставления с `ack`.
```json
// cmd/light
{ "cmd_id": "c-1", "power": "on", "brightness": 75 }
{ "cmd_id": "c-2", "power": "off" }

// cmd/filter | cmd/pump
{ "power": "on", "intensity": 50 }        // intensity только для pump

// cmd/heater
{ "power": "on", "mode": "auto", "target_c": 25.5 }
{ "power": "on", "mode": "manual" }

// cmd/feeder
{ "cmd_id": "c-9", "action": "feed", "portions": 2 }
```

## Правила обработки на backend

1. `telemetry` → запись в таблицу `telemetry`, рассылка в WebSocket, проверка порогов.
2. Нарушение порога (значение вне [min,max] или устройство offline) → создание `alert`
   и отправка push (с антидребезгом, чтобы не слать один и тот же алерт непрерывно).
3. `state/*` → обновление таблицы `actuator_state` (последнее известное состояние).
4. REST-запрос управления → публикация `cmd/*`; ack (если пришёл) логируется.
5. Планировщик по расписанию публикует `cmd/feeder` (кормление) и `cmd/light` (сценарии света).
