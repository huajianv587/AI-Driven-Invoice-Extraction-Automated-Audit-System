from __future__ import annotations

import json

import pytest

import api_server
from src.api.app import readiness
from src.runtime_preflight import (
    REQUIRED_SCHEMA_TABLES,
    build_frontend_api_base_url,
    ensure_runtime_preflight,
)


def base_cfg(**overrides):
    cfg = {
        "APP_ENV": "local",
        "FRONTEND_ORIGIN": "http://127.0.0.1:3000",
        "AUTH_JWT_SECRET": "unit-test-secret",
        "AUTH_BOOTSTRAP_ADMIN_PASSWORD": "UnitTestPass123!",
        "AUTH_COOKIE_SECURE": False,
        "AUTH_COOKIE_DOMAIN": "",
        "NEXT_PUBLIC_API_BASE_URL": "",
        "API_PORT": 8009,
    }
    cfg.update(overrides)
    return cfg


class FakeReadinessDB:
    def __init__(self, *, tracked: bool, missing_tables: list[str] | None = None):
        self.tracked = tracked
        self.missing_tables = set(missing_tables or [])

    def fetch_one(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        params = params or ()
        if "select 1 as ok" in text:
            return {"ok": 1}
        if "from information_schema.tables" in text and "table_name = %s" in text:
            table_name = params[0]
            if table_name == "app_schema_migrations":
                return {"table_count": 1 if self.tracked else 0}
            return {"table_count": 0}
        if "from app_schema_migrations" in text:
            return {"file_name": "13_add_idempotency_and_operation_locks.sql", "applied_at": "2026-04-17 10:00:00"}
        return {}

    def fetch_all(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        params = params or ()
        if "from information_schema.tables" in text and "table_name in" in text:
            return [{"table_name": table} for table in params if table not in self.missing_tables]
        return []


def test_build_frontend_api_base_url_defaults_to_same_origin_proxy_in_production():
    cfg = base_cfg(
        APP_ENV="production",
        FRONTEND_ORIGIN="https://invoice.example.com",
        AUTH_COOKIE_SECURE=True,
    )
    assert build_frontend_api_base_url(cfg, public_host="localhost") == "https://invoice.example.com/api"


def test_build_frontend_api_base_url_preserves_explicit_split_origin():
    cfg = base_cfg(
        APP_ENV="production",
        FRONTEND_ORIGIN="https://app.invoice.example.com",
        NEXT_PUBLIC_API_BASE_URL="https://api.invoice.example.com",
        AUTH_COOKIE_SECURE=True,
    )
    assert build_frontend_api_base_url(cfg, public_host="localhost") == "https://api.invoice.example.com"


def test_runtime_preflight_rejects_demo_production_settings():
    cfg = base_cfg(
        APP_ENV="production",
        FRONTEND_ORIGIN="https://invoice.example.com",
        AUTH_JWT_SECRET="change-me-local-dev-secret",
        AUTH_BOOTSTRAP_ADMIN_PASSWORD="ChangeMe123!",
        AUTH_COOKIE_SECURE=False,
        AUTH_PUBLIC_READONLY_DEMO=True,
    )
    with pytest.raises(RuntimeError) as exc_info:
        ensure_runtime_preflight(cfg, context="FastAPI API")
    assert "AUTH_JWT_SECRET" in str(exc_info.value)
    assert "AUTH_BOOTSTRAP_ADMIN_PASSWORD" in str(exc_info.value)
    assert "AUTH_COOKIE_SECURE" in str(exc_info.value)
    assert "AUTH_PUBLIC_READONLY_DEMO" in str(exc_info.value)


def test_runtime_preflight_allows_split_origin_with_shared_cookie_domain():
    cfg = base_cfg(
        APP_ENV="production",
        FRONTEND_ORIGIN="https://app.invoice.example.com",
        NEXT_PUBLIC_API_BASE_URL="https://api.invoice.example.com",
        AUTH_COOKIE_DOMAIN=".invoice.example.com",
        AUTH_COOKIE_SECURE=True,
    )
    ensure_runtime_preflight(cfg, context="FastAPI API")


def test_runtime_preflight_rejects_missing_required_integrations():
    cfg = base_cfg(
        APP_ENV="production",
        FRONTEND_ORIGIN="https://invoice.example.com",
        AUTH_COOKIE_SECURE=True,
        DIFY_REQUIRED=True,
        EMAIL_ALERT_REQUIRED=True,
        FEISHU_SYNC_REQUIRED=True,
        FEISHU_SYNC_MODE="off",
    )
    with pytest.raises(RuntimeError) as exc_info:
        ensure_runtime_preflight(cfg, context="FastAPI API")
    message = str(exc_info.value)
    assert "DIFY_REQUIRED" in message
    assert "EMAIL_ALERT_REQUIRED" in message
    assert "FEISHU_SYNC_REQUIRED" in message


def test_readiness_returns_503_when_schema_tracking_is_missing():
    response = readiness(cfg=base_cfg(), db=FakeReadinessDB(tracked=False))
    payload = json.loads(response.body)
    assert response.status_code == 503
    assert payload["ok"] is False
    assert payload["checks"]["schema"]["ok"] is False


def test_readiness_returns_200_when_db_and_schema_are_ready():
    response = readiness(cfg=base_cfg(), db=FakeReadinessDB(tracked=True, missing_tables=[]))
    payload = json.loads(response.body)
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["checks"]["database"]["ok"] is True
    assert payload["checks"]["schema"]["latest_file"] == "13_add_idempotency_and_operation_locks.sql"


def test_readiness_returns_503_when_required_tables_are_missing():
    response = readiness(cfg=base_cfg(), db=FakeReadinessDB(tracked=True, missing_tables=[REQUIRED_SCHEMA_TABLES[0]]))
    payload = json.loads(response.body)
    assert response.status_code == 503
    assert REQUIRED_SCHEMA_TABLES[0] in payload["checks"]["schema"]["detail"]


def test_api_server_main_blocks_invalid_production_before_uvicorn(monkeypatch):
    called = {"uvicorn": False}
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://invoice.example.com")
    monkeypatch.setenv("AUTH_JWT_SECRET", "change-me-local-dev-secret")
    monkeypatch.setenv("AUTH_BOOTSTRAP_ADMIN_PASSWORD", "ChangeMe123!")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "False")
    monkeypatch.delenv("NEXT_PUBLIC_API_BASE_URL", raising=False)
    monkeypatch.setattr(api_server.uvicorn, "run", lambda *args, **kwargs: called.__setitem__("uvicorn", True))

    with pytest.raises(RuntimeError):
        api_server.main()
    assert called["uvicorn"] is False
