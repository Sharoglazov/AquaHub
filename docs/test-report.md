# Отчёт о тестировании — AquaControl

Дата прогона: 2026-09-28. Окружение: Windows 10, Python 3.11 (venv), pytest 8.3.4.

## 1. Резюме

| Уровень | Инструмент | Тестов | Результат |
|---------|-----------|--------|-----------|
| Модульные + интеграционные (backend, физика) | pytest | **34** | 34 passed (~1.3 c) |
| Сквозной (E2E) с реальным брокером | `scripts/e2e_check.py` | **9 проверок** | все пройдены |

Тестами покрыты все ключевые требования прототипа: сбор 5 параметров, автокормление и
управление актуаторами, хранение телеметрии, пороги и push-уведомления, восстановление
после нарушения.

## 2. Модульные и интеграционные тесты

Запуск:

```bash
cd backend && python -m pytest -q
```

Итог: `34 passed`. Брокер не требуется — MQTT-хендлеры вызываются напрямую, БД —
in-memory SQLite (`StaticPool`), а push и WebSocket-хаб подменяются заглушками для проверки
побочных эффектов.

### 2.1 Физическая модель устройства — `test_physics.py` (12)

| Тест | Что проверяет |
|------|---------------|
| `test_heater_auto_raises_temperature_towards_target` | Нагреватель в авторежиме поднимает температуру к уставке |
| `test_heater_stuck_off_fault_prevents_heating` | Неисправность `heater_stuck_off`: нагрева нет, дрейф к среде |
| `test_feeding_raises_tds_and_lowers_ph` | Кормление повышает TDS и снижает pH, счётчик порций растёт |
| `test_filter_off_keeps_tds_elevated_longer` | Фильтр ускоряет очистку от растворённых веществ |
| `test_light_command_changes_illuminance` | Включение света повышает освещённость |
| `test_light_brightness_clamped` | Яркость ограничивается диапазоном 0–100 |
| `test_apply_command_unknown_actuator` | Неизвестный актуатор → ошибка |
| `test_feeder_requires_feed_action` | Кормушка требует action=feed |
| `test_build_state_shapes` | Форма retained-состояния актуаторов |
| `test_read_sensors_returns_all_metrics` | Датчики возвращают все 5 метрик (float) |
| `test_water_level_auto_topoff_recovers` | Автодолив (ATO) восстанавливает уровень |
| `test_ato_off_fault_lets_level_fall` | Неисправность `ato_off`: уровень падает |

### 2.2 MQTT-ingest, пороги и алерты — `test_ingest_alerts.py` (8)

| Тест | Что проверяет |
|------|---------------|
| `test_telemetry_ingest_stores_samples` | Телеметрия из MQTT сохраняется по метрикам |
| `test_breach_opens_alert_and_pushes` | Нарушение порога открывает алерт (severity=critical) + push + кадр WS |
| `test_alert_debounce_suppresses_repeat_push` | Устойчивое нарушение → 1 push, а не поток |
| `test_recovery_resolves_alert` | Возврат в норму закрывает алерт (`resolved_at`) |
| `test_status_offline_raises_device_alert` | LWT/offline поднимает системный алерт устройства |
| `test_status_online_resolves_device_alert` | Возврат online закрывает системный алерт |
| `test_actuator_state_persisted` | Состояние актуатора сохраняется (JSON) |
| `test_disabled_threshold_does_not_alert` | Выключенный порог не порождает алертов |

### 2.3 REST API — `test_api.py` (14)

| Тест | Что проверяет |
|------|---------------|
| `test_health` | `/health` отвечает |
| `test_create_and_get_device` | Создание и чтение устройства (кириллица в имени) |
| `test_get_missing_device_404` | Несуществующее устройство → 404 |
| `test_new_device_seeds_default_thresholds` | Новое устройство получает пороги по умолчанию |
| `test_update_threshold` | Обновление порога |
| `test_update_unknown_metric_400` | Неизвестная метрика → 400 |
| `test_control_light_publishes_command` | Команда света публикует MQTT в `cmd/light` с `cmd_id` |
| `test_control_feed_publishes_feed_action` | Кормление публикует `action=feed` в `cmd/feeder` |
| `test_control_validation_rejects_bad_brightness` | Яркость 500 → 422 |
| `test_pump_intensity_validation` | Интенсивность −5 → 422 |
| `test_feeding_schedule_crud` | Расписание кормления: создать/список/удалить |
| `test_light_scenario_crud` | Сценарий света: создать/проверить |
| `test_register_push_token` | Регистрация push-токена, идемпотентность |
| `test_telemetry_latest_empty` | Пустой снимок телеметрии до данных |

## 3. Сквозное тестирование (E2E)

Запуск (нужен брокер на `localhost:1883`):

```bash
python scripts/e2e_check.py
```

Скрипт поднимает backend в процессе (uvicorn, порт 8010) и запускает **настоящий агент
устройства** (`tank-e2e`, `time_scale=30`) против реального Mosquitto — то есть проверяет
всю цепочку `устройство → брокер → backend → БД → REST`, а не изолированные модули.

| # | Проверка | Итог |
|---|----------|------|
| 1 | `backend /health responds` | ✅ |
| 2 | `telemetry flows device → broker → backend → REST` | ✅ |
| 3 | `device reported online` | ✅ |
| 4 | `actuator state stored (>=1 actuator)` | ✅ |
| 5 | `feed command accepted (HTTP 200)` | ✅ |
| 6 | `feeder portions increased after command (round-trip)` | ✅ |
| 7 | `light command reflected in actuator state` | ✅ |
| 8 | `threshold breach opened an active alert` | ✅ |
| 9 | `alert resolves when value back in range` | ✅ |

Итог: `ALL 9 E2E CHECKS PASSED`.

## 4. Что проверено вручную

- **Swagger UI** (`/docs`) — интерактивный вызов всех эндпоинтов, схемы отображаются корректно.
- **WebSocket** (`/ws/telemetry`) — кадры `telemetry/status/state/alert` приходят при работе устройства.
- **Docker Compose** — весь стек поднимается одной командой; проброс порта 9001 на данном
  Windows-хосте недоступен (занят системой) и убирается без влияния на работу — задокументировано
  в [`RUNNING.md`](RUNNING.md).

## 5. Известные ограничения

- Android-приложение проверено на уровне сборки исходников; UI-тесты (Espresso/Compose) не входят
  в объём прототипа.
- E2E требует внешнего брокера (намеренно — проверяется реальный MQTT-транспорт).
- В консоли Windows кириллица в логах может отображаться искажённо (cosmetic); данные хранятся и
  отдаются в UTF-8 корректно (подтверждено через REST и тесты с кириллицей).

## 6. Как воспроизвести

```bash
# модульные + интеграционные
cd backend && pip install -r requirements.txt && python -m pytest -q

# E2E (в отдельном терминале — брокер, см. RUNNING.md)
python scripts/e2e_check.py
```
