"""WebSocket hub for live telemetry/alert fan-out to connected apps.

The MQTT ingest runs on paho's network thread, so broadcasts are scheduled onto
the FastAPI event loop with ``run_coroutine_threadsafe``.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

log = logging.getLogger("ws")


class WebSocketHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = asyncio.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        log.info("ws client connected (%d total)", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        log.info("ws client disconnected (%d total)", len(self._clients))

    async def _broadcast(self, message: str) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001 — client vanished mid-send
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    def publish(self, kind: str, data: dict) -> None:
        """Thread-safe broadcast. Safe to call from the MQTT/scheduler threads."""
        if self._loop is None:
            return
        message = json.dumps({"type": kind, "data": data}, default=str)
        asyncio.run_coroutine_threadsafe(self._broadcast(message), self._loop)


hub = WebSocketHub()
