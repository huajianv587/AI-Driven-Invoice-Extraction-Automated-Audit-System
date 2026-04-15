from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config


REQUIRED_CONFIRMATION = "RESET_DEMO_DATA_AND_CALL_REAL_INTEGRATIONS"
REQUIRED_APP_ENV = "local"
LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}
PRODUCTION_WORDS = ("prod", "production", "live", "customer")


def _truthy(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _truthy_value(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _contains_production_marker(value: object) -> bool:
    text = str(value or "").strip().lower()
    return any(marker in text for marker in PRODUCTION_WORDS)


def _url_host(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    return (parsed.hostname or "").strip().lower()


def validate_deep_regression_safety() -> dict:
    explicit_values = {
        "APP_ENV": os.environ.get("APP_ENV"),
        "ALLOW_REAL_INTEGRATION_TESTS": os.environ.get("ALLOW_REAL_INTEGRATION_TESTS"),
        "WEB_DEEP_RESET_DEMO_DB": os.environ.get("WEB_DEEP_RESET_DEMO_DB"),
        "WEB_DEEP_CONFIRM": os.environ.get("WEB_DEEP_CONFIRM"),
    }
    load_env(override=False)
    cfg = load_flat_config()
    app_env = str(explicit_values["APP_ENV"] or "").strip().lower()
    external_prefix = str(os.getenv("WEB_DEEP_EXTERNAL_PREFIX", "")).strip()
    failures: list[str] = []

    if explicit_values["APP_ENV"] is None or not app_env:
        failures.append("APP_ENV must be explicitly set to local in the process environment.")
    elif app_env != REQUIRED_APP_ENV:
        failures.append(f"APP_ENV must be exactly {REQUIRED_APP_ENV!r} for reset-style deep regression, got {app_env!r}.")
    if not _truthy_value(explicit_values["ALLOW_REAL_INTEGRATION_TESTS"]):
        failures.append("ALLOW_REAL_INTEGRATION_TESTS must be explicitly set to 1.")
    if not _truthy_value(explicit_values["WEB_DEEP_RESET_DEMO_DB"]):
        failures.append("WEB_DEEP_RESET_DEMO_DB must be explicitly set to 1.")
    if str(explicit_values["WEB_DEEP_CONFIRM"] or "").strip() != REQUIRED_CONFIRMATION:
        failures.append(f"WEB_DEEP_CONFIRM must equal {REQUIRED_CONFIRMATION}.")
    if not external_prefix or not any(token in external_prefix.upper() for token in ("TEST", "DEMO", "DEV")):
        failures.append("WEB_DEEP_EXTERNAL_PREFIX must contain TEST, DEMO, or DEV.")

    frontend_host = _url_host(cfg.get("FRONTEND_ORIGIN"))
    mysql_host = str(cfg.get("MYSQL_HOST") or "").strip().lower()
    if frontend_host not in LOCAL_HOSTS:
        failures.append(f"FRONTEND_ORIGIN host {frontend_host!r} is not localhost.")
    if mysql_host not in LOCAL_HOSTS:
        failures.append(f"MYSQL_HOST {mysql_host!r} is not localhost.")

    production_candidates = {
        "MYSQL_DB": cfg.get("MYSQL_DB"),
        "FRONTEND_ORIGIN": cfg.get("FRONTEND_ORIGIN"),
        "FEISHU_APP_TOKEN": cfg.get("FEISHU_APP_TOKEN"),
        "FEISHU_TABLE_ID": cfg.get("FEISHU_TABLE_ID"),
        "DIFY_WORKFLOW_ID": cfg.get("DIFY_WORKFLOW_ID"),
    }
    for name, value in production_candidates.items():
        if _contains_production_marker(value):
            failures.append(f"{name} appears production-like; deep regression refused.")

    summary = {
        "ok": not failures,
        "app_env": app_env,
        "external_prefix": external_prefix,
        "frontend_host": frontend_host,
        "mysql_host": mysql_host,
        "failures": failures,
    }
    if failures:
        raise RuntimeError(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    try:
        summary = validate_deep_regression_safety()
    except Exception as exc:
        print("[blocked] Deep regression safety guard refused to run.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        sys.exit(2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
