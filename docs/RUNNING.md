# Как запускать AquaControl

Три способа: весь стек в Docker, локальный запуск по компонентам
(для разработки) и прогон тестов.

---

## Вариант A. Весь стек в Docker 

Требуется Docker Desktop / Docker Engine с Compose v2.

```bash
cd deploy
docker compose up --build
```

Поднимутся три сервиса:

| Сервис  | Что это | Порты |
|---------|---------|-------|
| `broker`  | Mosquitto (MQTT + WebSocket) | 1883, 9001 |
| `backend` | FastAPI (REST + WS), MQTT-ingest, БД, планировщик | 8000 |
| `device`  | Эмулятор устройства `tank-01` | — |

Проверка:

- Swagger UI: <http://localhost:8000/docs>
- Здоровье: <http://localhost:8000/health>
- Последняя телеметрия: <http://localhost:8000/devices/tank-01/telemetry/latest>

> **Порт 9001** (MQTT-over-WebSocket) нужен только браузерным MQTT-клиентам. Если он занят
> или заблокирован на хосте, уберите его проброс в `deploy/docker-compose.yml` — на работу
> системы это не влияет (backend и устройство ходят через 1883).

Остановка: `Ctrl+C`, затем `docker compose down` (добавьте `-v`, чтобы удалить тома с данными).

### Демонстрация неисправностей

Чтобы увидеть срабатывание алертов, задайте устройству неисправность в
`docker-compose.yml` (сервис `device`):

```yaml
    environment:
      AQUA_FAULTS: "heater_stuck_off"   # температура не растёт → уйдёт ниже порога
      AQUA_TIME_SCALE: "20.0"           # ускорить физику, чтобы не ждать
```

Поддерживаются: `heater_stuck_off`, `ato_off` (не работает автодолив — падает уровень),
`ph_drift` (уползает pH).

---

## Вариант B. Локальный запуск по компонентам

Требуется Python 3.11+ и запущенный MQTT-брокер.

### 1. Брокер

Проще всего — в Docker:

```bash
docker run -it --rm -p 1883:1883 \
  -v "$PWD/deploy/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro" \
  eclipse-mosquitto:2
```

(На Windows/Git Bash добавьте перед командой `MSYS_NO_PATHCONV=1`, чтобы путь тома не искажался.)

### 2. Backend

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate    # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Настройки — через переменные окружения с префиксом `AQUA_` (см. `backend/app/config.py`):

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `AQUA_DATABASE_URL` | `sqlite:///./aqua.db` | Строка подключения к БД |
| `AQUA_BROKER_HOST` / `AQUA_BROKER_PORT` | `localhost` / `1883` | MQTT-брокер |
| `AQUA_API_KEY` | (пусто) | Если задан — защищает пишущие эндпоинты |
| `AQUA_PUSH_PROVIDER` | `console` | `console` / `fcm` / `none` |
| `AQUA_ALERT_DEBOUNCE_S` | `300` | Мин. интервал между повторными push |
| `AQUA_CORS_ORIGINS` | `*` | Разрешённые источники CORS |

### 3. Эмулятор устройства

В отдельном терминале:

```bash
cd firmware
pip install -r requirements.txt
AQUA_DEVICE_ID=tank-01 AQUA_BROKER_HOST=localhost python agent.py
```

Полезные переменные: `AQUA_TELEMETRY_INTERVAL` (сек), `AQUA_TIME_SCALE` (ускорение физики),
`AQUA_FAULTS` (см. выше).

---

## Вариант C. Android-приложение

Открыть каталог `android/` в **Android Studio** (Giraffe и новее). При первом открытии
Studio синхронизирует Gradle и при необходимости до-генерирует `gradle-wrapper.jar`.

> В репозиторий включён официальный `gradle/wrapper/gradle-wrapper.jar` (Gradle 8.9) и
> скрипты `gradlew` / `gradlew.bat`, так что сборка из командной строки тоже работает:
> `./gradlew :app:assembleDebug`. Требуется JDK 17 и Android SDK (compileSdk 34).

Адреса backend зашиты в `app/build.gradle.kts` через `BuildConfig`:

| Поле | Значение по умолчанию | Комментарий |
|------|-----------------------|-------------|
| `API_BASE_URL` | `http://10.0.2.2:8000` | `10.0.2.2` = localhost хоста из эмулятора Android |
| `WS_URL` | `ws://10.0.2.2:8000/ws/telemetry` | Живая телеметрия |
| `DEVICE_ID` | `tank-01` | Отображаемое устройство |
| `API_KEY` | (пусто) | Заполнить, если backend защищён ключом |

Для реального телефона замените `10.0.2.2` на IP-адрес машины с backend (в одной сети).

---

## Тесты

### Модульные и интеграционные (backend + физика), без брокера

```bash
cd backend
pip install -r requirements.txt
python -m pytest -q
```

Ожидаемо: **34 passed**. Покрывают физику модели, MQTT-ingest, пороги/алерты (включая
дебаунс и восстановление) и REST API. Брокер не нужен — хендлеры вызываются напрямую,
БД — in-memory SQLite.

### Сквозная проверка (E2E) с настоящим брокером

Нужен MQTT-брокер на `localhost:1883` (см. Вариант B, шаг 1). Затем:

```bash
python scripts/e2e_check.py
```

Скрипт поднимает backend в процессе и запускает агент устройства против брокера, после чего
проверяет: поток телеметрии до REST, статус online, сохранение состояния актуаторов,
доставку команды кормления (порции растут), команду света, открытие алерта по нарушению
порога и его закрытие при возврате в норму. Завершается ненулевым кодом на первой ошибке.

Подробности — в [`test-report.md`](test-report.md).
