"""Shared API dependencies: DB session and optional API-key auth."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session

__all__ = ["get_session", "require_api_key", "Session", "Depends"]


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Guard write/control endpoints. No-op when AQUA_API_KEY is unset (dev)."""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )
