"""FastAPI application entrypoint: wiring, lifespan, WebSocket, docs metadata."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import mqtt_client
from .api import alerts, control, devices, push, schedules, telemetry, thresholds
from .config import settings
from .db import init_db
from .services import scheduler
from .ws import hub

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    hub.bind_loop(asyncio.get_running_loop())
    mqtt_client.start()
    scheduler.start()
    yield
    scheduler.shutdown()
    mqtt_client.stop()


app = FastAPI(
    title="AquaControl API",
    version="1.0.0",
    description=(
        "REST API умного аквариума: телеметрия, ручное управление, пороги, "
        "алерты, расписания автокормления и сценарии освещения. "
        "Живые обновления — по WebSocket `/ws/telemetry`."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_origins == "*"
    else [o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (devices.router, telemetry.router, control.router, thresholds.router,
          alerts.router, schedules.router, push.router):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    """Live stream of telemetry/status/state/alert events (JSON frames)."""
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # ignore client input; keeps the socket open
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(ws)
