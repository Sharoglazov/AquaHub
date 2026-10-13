"""Push-notification providers.

A small provider abstraction so the alert pipeline stays decoupled from the
delivery channel:

* ``console`` — logs the notification (default; always works, demonstrable).
* ``fcm``     — Firebase Cloud Messaging via the legacy HTTP API using
  ``AQUA_FCM_SERVER_KEY``. This is the integration point for real Android push;
  if no key is configured it degrades to console.
* ``none``    — disabled.

Tokens are the app's FCM registration tokens, stored via ``POST /push/tokens``.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

from ..config import settings

log = logging.getLogger("notifications")


class PushProvider(ABC):
    @abstractmethod
    def send(self, tokens: list[str], title: str, body: str, data: dict | None = None) -> None:
        ...


class ConsolePushProvider(PushProvider):
    def send(self, tokens: list[str], title: str, body: str, data: dict | None = None) -> None:
        log.warning("[PUSH → %d device(s)] %s — %s | data=%s",
                    len(tokens), title, body, data or {})


class FcmPushProvider(PushProvider):
    ENDPOINT = "https://fcm.googleapis.com/fcm/send"

    def __init__(self, server_key: str) -> None:
        self._server_key = server_key

    def send(self, tokens: list[str], title: str, body: str, data: dict | None = None) -> None:
        if not tokens:
            return
        headers = {"Authorization": f"key={self._server_key}", "Content-Type": "application/json"}
        payload = {
            "registration_ids": tokens,
            "notification": {"title": title, "body": body},
            "data": data or {},
        }
        try:
            resp = httpx.post(self.ENDPOINT, json=payload, headers=headers, timeout=10.0)
            log.info("FCM send status=%s", resp.status_code)
        except httpx.HTTPError as exc:  # network issues shouldn't crash ingest
            log.error("FCM send failed: %s", exc)


def _build_provider() -> PushProvider:
    if settings.push_provider == "fcm" and settings.fcm_server_key:
        log.info("push provider: FCM")
        return FcmPushProvider(settings.fcm_server_key)
    if settings.push_provider == "none":
        log.info("push provider: disabled")
        return _NullProvider()
    log.info("push provider: console")
    return ConsolePushProvider()


class _NullProvider(PushProvider):
    def send(self, tokens: list[str], title: str, body: str, data: dict | None = None) -> None:
        return


provider: PushProvider = _build_provider()
