import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.routes import health


def test_liveness_returns_api_identity():
    assert health.liveness() == {"status": "ok", "service": settings.app_name}


def test_readiness_returns_connected_state(monkeypatch):
    monkeypatch.setattr(health, "check_mongo_connection", lambda: True)
    assert health.readiness() == {"status": "ready", "database": "connected"}


def test_readiness_returns_503_when_mongodb_is_unavailable(monkeypatch):
    monkeypatch.setattr(health, "check_mongo_connection", lambda: False)

    with pytest.raises(HTTPException) as error:
        health.readiness()

    assert error.value.status_code == 503
    assert error.value.detail == {"status": "not_ready", "database": "unavailable"}
