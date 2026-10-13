# Справочник REST API — AquaControl

Базовый URL прототипа: `http://localhost:8000` (в Docker — то же; из эмулятора Android —
`http://10.0.2.2:8000`).

Живая, всегда актуальная документация генерируется автоматически:

- **Swagger UI:** <http://localhost:8000/docs>
- **ReDoc:** <http://localhost:8000/redoc>
- **OpenAPI JSON:** <http://localhost:8000/openapi.json>

Этот файл — краткий обзор. Точные схемы полей смотрите в Swagger или в
[`backend/app/schemas.py`](../backend/app/schemas.py).

## Аутентификация

Если задан `AQUA_API_KEY`, все **изменяющие/управляющие** запросы требуют заголовок:

```
X-API-Key: <ключ>
```

Эндпоинты только для чтения (`GET`) остаются открытыми. По умолчанию ключ не задан —
API открыт (режим разработки).

## Формат и соглашения

- Тело запросов и ответов — JSON.
- Временные метки — ISO-8601 UTC (например `2026-09-25T12:00:00Z`).
- Ключи метрик: `temperature_c`, `ph`, `water_level_pct`, `illuminance_lux`, `tds_ppm`.
- Актуаторы: `light`, `filter`, `pump`, `heater`, `feeder`.
- Ошибки — стандартные коды FastAPI: `404` (не найдено), `400` (неизвестная метрика),
  `422` (ошибка валидации тела), `401` (нет/неверный API-ключ, когда он включён).

---

## Метаданные

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/health` | Проверка живости. `{"status":"ok"}` |

## Устройства

| Метод | Путь | Описание |
|-------|------|----------|
| `GET`  | `/devices` | Список устройств |
| `POST` | `/devices` 🔒 | Создать устройство (засеивает пороги по умолчанию). Тело: `{"id":"tank-01","name":"Гостиная"}` |
| `GET`  | `/devices/{device_id}` | Одно устройство (`404`, если нет) |
| `GET`  | `/devices/{device_id}/actuators` | Текущее состояние всех актуаторов |

`DeviceOut`: `{ id, name, online, last_seen }`.

## Телеметрия

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/devices/{device_id}/telemetry/latest` | Последний снимок: `{ device_id, ts, metrics: { <metric>: value } }` |
| `GET` | `/devices/{device_id}/telemetry/history` | Исторические ряды для графиков |

Параметры `history`:

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `metric` | string | (все) | Одна метрика; если не задана — все пять |
| `start`  | datetime | — | Начало интервала |
| `end`    | datetime | — | Конец интервала |
| `max_points` | int (10–5000) | 500 | Прореживание: макс. точек на ряд |

Ответ: список `MetricSeries` = `{ metric, points: [{ ts, value }] }`.

## Управление (публикует MQTT-команду)

Все — `POST /devices/{device_id}/control/...`, требуют API-ключ (когда включён).
Ответ единый — `CommandResult`: `{ ok, published_topic, payload }` (в payload входит
сгенерированный `cmd_id`).

| Путь | Тело | Примечание |
|------|------|------------|
| `/control/light`  | `{ "power": "on|off", "brightness": 0..100 }` | Оба поля опциональны |
| `/control/filter` | `{ "power": "on|off" }` | |
| `/control/pump`   | `{ "power": "on|off", "intensity": 0..100 }` | Оба поля опциональны |
| `/control/heater` | `{ "power": "on|off", "mode": "auto|manual", "target_c": 15..32 }` | Все поля опциональны |
| `/control/feed`   | `{ "portions": 1..10 }` | Разовое кормление |

Пример:

```bash
curl -X POST http://localhost:8000/devices/tank-01/control/light \
  -H "Content-Type: application/json" \
  -d '{"power":"on","brightness":60}'
```

## Пороговые значения

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/devices/{device_id}/thresholds` | Список порогов (засеивает устройство при первом обращении) |
| `PUT` | `/devices/{device_id}/thresholds/{metric}` 🔒 | Обновить порог. Тело: `{ "min_value": 24.0, "max_value": 27.0, "enabled": true }` (все поля опциональны). `400` для неизвестной метрики |

Пороги по умолчанию: temperature_c `24–27`, ph `6.5–7.8`, water_level_pct `80–100`,
tds_ppm `100–300`, illuminance_lux `0–2000` (выключен).

## Алерты

| Метод | Путь | Описание |
|-------|------|----------|
| `GET`  | `/devices/{device_id}/alerts` | История алертов. Параметры: `active` (bool), `limit` (1–1000, по умолчанию 100) |
| `POST` | `/devices/{device_id}/alerts/{alert_id}/resolve` 🔒 | Вручную закрыть алерт |

`AlertOut`: `{ id, device_id, metric, severity, message, value, threshold_min, threshold_max, active, created_at, resolved_at }`.
`metric = null` — системный алерт (например, устройство offline). `severity`: `critical` для
temperature_c/water_level_pct, иначе `warning`.

## Расписания (автоматизация)

### Автокормление

| Метод | Путь | Описание |
|-------|------|----------|
| `GET`    | `/devices/{device_id}/schedules/feeding` | Список расписаний |
| `POST`   | `/devices/{device_id}/schedules/feeding` 🔒 | Создать. Тело: `{ "hour":8, "minute":30, "portions":2, "enabled":true }` |
| `DELETE` | `/devices/{device_id}/schedules/feeding/{schedule_id}` 🔒 | Удалить |

### Сценарии освещения

| Метод | Путь | Описание |
|-------|------|----------|
| `GET`    | `/devices/{device_id}/schedules/light` | Список сценариев |
| `POST`   | `/devices/{device_id}/schedules/light` 🔒 | Создать. Тело: `{ "on_hour":9,"on_minute":0,"off_hour":21,"off_minute":0,"brightness":80,"enabled":true }` |
| `DELETE` | `/devices/{device_id}/schedules/light/{scenario_id}` 🔒 | Удалить |

Любое изменение расписаний немедленно пересобирает задания планировщика (`sync_all()`).

## Push-токены

| Метод | Путь | Описание |
|-------|------|----------|
| `POST`   | `/push/tokens` 🔒 | Регистрация токена. Тело: `{ "token":"...", "platform":"android|ios|web" }`. Идемпотентно, `201` |
| `DELETE` | `/push/tokens?token=...` 🔒 | Удалить токен, `204` |

## WebSocket — живые обновления

```
ws://localhost:8000/ws/telemetry
```

Сервер шлёт JSON-кадры вида `{ "kind": <тип>, "data": {...} }`, где `kind` ∈
`telemetry | status | state | alert`. Клиентские сообщения игнорируются (сокет держится открытым).
Приложение использует этот канал для мгновенного обновления дашборда; графики и снимки
дополнительно подтягиваются через REST.

🔒 — требует `X-API-Key`, когда задан `AQUA_API_KEY`.
