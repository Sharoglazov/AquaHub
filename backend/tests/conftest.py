"""Test fixtures.

Each test gets an isolated in-memory SQLite database and a FastAPI TestClient
with MQTT publishing and the background scheduler stubbed out, so the API layer
can be exercised without a broker. MQTT ingest itself is tested separately by
calling the handlers directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Make the backend package importable when pytest is run from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db as db_module  # noqa: E402


@pytest.fixture()
def session_factory():
    """Fresh in-memory DB, shared across connections within one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False,
                                       expire_on_commit=False, future=True)
    # Point the whole app (models, services, ingest) at this engine.
    db_module.engine = engine
    db_module.SessionLocal = TestingSessionLocal
    db_module.Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


@pytest.fixture()
def published(monkeypatch):
    """Capture MQTT publishes instead of hitting a broker."""
    calls: list[tuple[str, dict, int]] = []

    def fake_publish(topic, payload, qos=1):
        calls.append((topic, payload, qos))

    monkeypatch.setattr("app.mqtt_client.publish", fake_publish)
    monkeypatch.setattr("app.services.control.mqtt_client.publish", fake_publish)
    return calls


@pytest.fixture()
def client(session_factory, published, monkeypatch):
    # Stub scheduler + MQTT lifecycle so startup needs no broker.
    monkeypatch.setattr("app.services.scheduler.start", lambda: None)
    monkeypatch.setattr("app.services.scheduler.shutdown", lambda: None)
    monkeypatch.setattr("app.services.scheduler.sync_all", lambda: None)
    monkeypatch.setattr("app.mqtt_client.start", lambda: None)
    monkeypatch.setattr("app.mqtt_client.stop", lambda: None)
    monkeypatch.setattr("app.db.init_db", lambda: None)

    from app.main import app

    with TestClient(app) as c:
        yield c
