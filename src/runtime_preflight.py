from __future__ import annotations

from typing import Any, Dict, List, Sequence
from urllib.parse import urlparse


DEFAULT_JWT_SECRET = "change-me-local-dev-secret"
DEFAULT_BOOTSTRAP_ADMIN_PASSWORD = "ChangeMe123!"
LOCAL_HOSTS = {"", "127.0.0.1", "localhost", "0.0.0.0", "::1"}
REQUIRED_SCHEMA_TABLES = (
    "invoices",
    "invoice_items",
    "invoice_events",
    "app_users",
    "app_refresh_tokens",
    "app_security_events",
    "app_intake_uploads",
    "invoice_review_tasks",
)


def _cfg_value(cfg: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = cfg.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _cfg_int(cfg: Dict[str, Any], *keys: str, default: int) -> int:
    for key in keys:
        value = cfg.get(key)
        if value in (None, ""):
            continue
        return int(value)
    return default


def _cfg_bool(cfg: Dict[str, Any], *keys: str, default: bool = False) -> bool:
    for key in keys:
        value = cfg.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "1", "yes"}
    return default


def _parsed_url(value: str):
    text = str(value or "").strip()
    if not text:
        return None
    return urlparse(text if "://" in text else f"http://{text}")


def _valid_absolute_url(value: str) -> bool:
    parsed = _parsed_url(value)
    return bool(parsed and parsed.scheme and parsed.netloc)


def url_host(value: str) -> str:
    parsed = _parsed_url(value)
    return (parsed.hostname or "").strip().lower() if parsed else ""


def url_scheme(value: str) -> str:
    parsed = _parsed_url(value)
    return (parsed.scheme or "").strip().lower() if parsed else ""


def is_local_host(host: str) -> bool:
    return str(host or "").strip().lower() in LOCAL_HOSTS


def cookie_domain_matches_host(cookie_domain: str, host: str) -> bool:
    normalized_host = str(host or "").strip().lower()
    normalized_domain = str(cookie_domain or "").strip().lower().lstrip(".")
    if not normalized_host or not normalized_domain:
        return False
    return normalized_host == normalized_domain or normalized_host.endswith(f".{normalized_domain}")


def build_frontend_api_base_url(cfg: Dict[str, Any], *, public_host: str = "127.0.0.1") -> str:
    explicit = _cfg_value(cfg, "NEXT_PUBLIC_API_BASE_URL", "public_api_base_url")
    if explicit:
        return explicit.rstrip("/")

    app_env = _cfg_value(cfg, "APP_ENV", "app_env").lower() or "local"
    frontend_origin = _cfg_value(cfg, "FRONTEND_ORIGIN", "frontend_origin").rstrip("/")
    if app_env == "production" and frontend_origin and not is_local_host(url_host(frontend_origin)):
        return f"{frontend_origin}/api"

    host = str(public_host or "127.0.0.1").strip() or "127.0.0.1"
    api_port = _cfg_int(cfg, "API_PORT", "api_port", default=8009)
    return f"http://{host}:{api_port}"


def runtime_config_issues(cfg: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    app_env = _cfg_value(cfg, "APP_ENV", "app_env").lower() or "local"
    frontend_origin = _cfg_value(cfg, "FRONTEND_ORIGIN", "frontend_origin")
    jwt_secret = _cfg_value(cfg, "AUTH_JWT_SECRET", "auth_jwt_secret")
    bootstrap_password = _cfg_value(cfg, "AUTH_BOOTSTRAP_ADMIN_PASSWORD", "auth_bootstrap_admin_password")
    cookie_secure = _cfg_value(cfg, "AUTH_COOKIE_SECURE", "auth_cookie_secure").lower()
    cookie_domain = _cfg_value(cfg, "AUTH_COOKIE_DOMAIN", "auth_cookie_domain")
    public_api_base_url = _cfg_value(cfg, "NEXT_PUBLIC_API_BASE_URL", "public_api_base_url")
    public_readonly_demo = _cfg_bool(cfg, "AUTH_PUBLIC_READONLY_DEMO", "auth_public_readonly_demo")
    dify_required = _cfg_bool(cfg, "DIFY_REQUIRED", "dify_required")
    email_required = _cfg_bool(cfg, "EMAIL_ALERT_REQUIRED", "email_alert_required")
    feishu_required = _cfg_bool(cfg, "FEISHU_SYNC_REQUIRED", "feishu_sync_required")

    if not frontend_origin:
        issues.append("FRONTEND_ORIGIN is required.")
    elif not _valid_absolute_url(frontend_origin):
        issues.append(f"FRONTEND_ORIGIN must be an absolute URL, got {frontend_origin!r}.")

    if public_api_base_url and not _valid_absolute_url(public_api_base_url):
        issues.append(f"NEXT_PUBLIC_API_BASE_URL must be an absolute URL, got {public_api_base_url!r}.")

    if app_env != "production":
        return issues

    if jwt_secret == DEFAULT_JWT_SECRET:
        issues.append("AUTH_JWT_SECRET still uses the local demo default.")
    if bootstrap_password == DEFAULT_BOOTSTRAP_ADMIN_PASSWORD:
        issues.append("AUTH_BOOTSTRAP_ADMIN_PASSWORD still uses the local demo default.")
    if cookie_secure not in {"true", "1", "yes"}:
        issues.append("AUTH_COOKIE_SECURE must be true in production.")
    if public_readonly_demo:
        issues.append("AUTH_PUBLIC_READONLY_DEMO must be disabled in production.")

    frontend_host = url_host(frontend_origin)
    frontend_scheme = url_scheme(frontend_origin)
    if not frontend_host or is_local_host(frontend_host):
        issues.append(f"FRONTEND_ORIGIN host {frontend_host or '-'} is not valid for production.")
    if frontend_scheme != "https":
        issues.append("FRONTEND_ORIGIN must use https in production.")

    if public_api_base_url:
        api_host = url_host(public_api_base_url)
        api_scheme = url_scheme(public_api_base_url)
        if not api_host or is_local_host(api_host):
            issues.append(f"NEXT_PUBLIC_API_BASE_URL host {api_host or '-'} is not valid for production.")
        if api_scheme != "https":
            issues.append("NEXT_PUBLIC_API_BASE_URL must use https in production.")
        if api_host and frontend_host and api_host != frontend_host:
            if not cookie_domain:
                issues.append(
                    "AUTH_COOKIE_DOMAIN is required when NEXT_PUBLIC_API_BASE_URL uses a different host from FRONTEND_ORIGIN."
                )
            elif not (
                cookie_domain_matches_host(cookie_domain, frontend_host)
                and cookie_domain_matches_host(cookie_domain, api_host)
            ):
                issues.append(
                    "AUTH_COOKIE_DOMAIN must cover both FRONTEND_ORIGIN and NEXT_PUBLIC_API_BASE_URL hosts."
                )

    if dify_required:
        if not _cfg_value(cfg, "DIFY_API_KEY", "dify_api_key"):
            issues.append("DIFY_REQUIRED is enabled but DIFY_API_KEY is missing.")
        if not _cfg_value(cfg, "DIFY_WORKFLOW_ID", "dify_workflow_id"):
            issues.append("DIFY_REQUIRED is enabled but DIFY_WORKFLOW_ID is missing.")

    if email_required:
        if not _cfg_value(cfg, "SMTP_HOST"):
            issues.append("EMAIL_ALERT_REQUIRED is enabled but SMTP_HOST is missing.")
        if not _cfg_value(cfg, "SMTP_FROM_EMAIL", "SMTP_USER"):
            issues.append("EMAIL_ALERT_REQUIRED is enabled but SMTP_FROM_EMAIL/SMTP_USER is missing.")

    if feishu_required:
        if _cfg_value(cfg, "FEISHU_SYNC_MODE") != "inline":
            issues.append("FEISHU_SYNC_REQUIRED requires FEISHU_SYNC_MODE=inline.")
        for key in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_APP_TOKEN", "FEISHU_TABLE_ID"):
            if not _cfg_value(cfg, key):
                issues.append(f"FEISHU_SYNC_REQUIRED is enabled but {key} is missing.")

    return issues


def ensure_runtime_preflight(cfg: Dict[str, Any], *, context: str) -> None:
    issues = runtime_config_issues(cfg)
    if not issues:
        return
    issue_text = "; ".join(issues)
    raise RuntimeError(f"{context} startup blocked by configuration preflight: {issue_text}")


def _schema_state(db) -> Dict[str, Any]:
    exists_row = db.fetch_one(
        """
        SELECT COUNT(*) AS table_count
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = %s
        """,
        ("app_schema_migrations",),
    ) or {}
    if int(exists_row.get("table_count") or 0) == 0:
        return {"tracked": False, "latest_file": None, "applied_at": None}

    latest = db.fetch_one(
        """
        SELECT file_name AS file_name, applied_at AS applied_at
        FROM app_schema_migrations
        ORDER BY updated_at DESC, file_name DESC
        LIMIT 1
        """
    ) or {}
    return {
        "tracked": True,
        "latest_file": latest.get("file_name"),
        "applied_at": str(latest.get("applied_at") or "") or None,
    }


def _missing_tables(db, required_tables: Sequence[str]) -> List[str]:
    if not required_tables:
        return []
    placeholders = ", ".join(["%s"] * len(required_tables))
    rows = db.fetch_all(
        f"""
        SELECT table_name AS table_name
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name IN ({placeholders})
        """,
        tuple(required_tables),
    )
    existing = {str(row.get("table_name") or "") for row in rows}
    return [table for table in required_tables if table not in existing]


def build_readiness_report(db, cfg: Dict[str, Any]) -> Dict[str, Any]:
    checks: Dict[str, Dict[str, Any]] = {}
    config_issues = runtime_config_issues(cfg)
    checks["config"] = {
        "ok": not config_issues,
        "detail": "ready" if not config_issues else "; ".join(config_issues),
    }

    db_error = ""
    schema_state = {"tracked": False, "latest_file": None, "applied_at": None}
    missing_tables: List[str] = list(REQUIRED_SCHEMA_TABLES)

    try:
        db.fetch_one("SELECT 1 AS ok")
        missing_tables = _missing_tables(db, REQUIRED_SCHEMA_TABLES)
        schema_state = _schema_state(db)
    except Exception as exc:
        db_error = f"{type(exc).__name__}: {exc}"

    checks["database"] = {
        "ok": not db_error,
        "detail": "ready" if not db_error else db_error,
    }
    checks["schema"] = {
        "ok": not db_error and not missing_tables and bool(schema_state["tracked"]),
        "detail": (
            "ready"
            if not db_error and not missing_tables and schema_state["tracked"]
            else (
                f"missing tables: {', '.join(missing_tables)}"
                if not db_error and missing_tables
                else "schema tracking table app_schema_migrations is missing"
            )
        ),
        "latest_file": schema_state["latest_file"],
        "applied_at": schema_state["applied_at"],
    }
    return {
        "ok": all(check.get("ok") for check in checks.values()),
        "app_env": _cfg_value(cfg, "APP_ENV", "app_env").lower() or "local",
        "checks": checks,
    }
