from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_env(override: bool = False) -> Optional[Path]:
    candidates = [
        project_root() / ".env",
        project_root() / ".env.local",
    ]
    for candidate in candidates:
        if candidate.exists():
            load_dotenv(candidate, override=override)
            return candidate
    return None


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _pick(name: str, default: Optional[str] = None) -> Optional[str]:
    value = _clean(os.getenv(name))
    if value in (None, ""):
        return default
    return value


def _pick_bool(name: str, default: bool) -> bool:
    raw = _pick(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ProductSettings:
    app_name: str
    app_env: str
    app_secret_key: str
    api_host: str
    api_port: int
    api_base_url: str
    worker_id: str
    task_poll_interval_sec: float
    task_retry_limit: int
    storage_dir: str
    upload_dir: str
    processed_dir: str
    auth_session_ttl_hours: int
    auto_review_confidence_threshold: float
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_db: str
    ocr_base_url: str
    ocr_retry_max: int
    ocr_retry_sleep_sec: float
    dify_api_key: str
    dify_base_url: str
    dify_image_key: str
    dify_workflow_id: str
    dify_retry_max: int
    dify_retry_sleep_sec: float
    feishu_app_id: str
    feishu_app_secret: str
    feishu_app_token: str
    feishu_table_id: str
    feishu_sync_mode: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    smtp_from_name: str
    smtp_from_email: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    alert_fallback_to: str
    ui_port: int
    anomaly_form_base_url: str
    admin_username: str
    admin_password: str
    operator_username: str
    operator_password: str
    reviewer_username: str
    reviewer_password: str

    def db_kwargs(self) -> Dict[str, Any]:
        return {
            "host": self.mysql_host,
            "port": self.mysql_port,
            "user": self.mysql_user,
            "password": self.mysql_password,
            "db": self.mysql_db,
            "connect_timeout": 10,
            "autocommit": False,
        }

    def legacy_flat_config(self) -> Dict[str, Any]:
        return {
            "mysql_host": self.mysql_host,
            "mysql_port": self.mysql_port,
            "mysql_user": self.mysql_user,
            "mysql_password": self.mysql_password,
            "mysql_db": self.mysql_db,
            "MYSQL_HOST": self.mysql_host,
            "MYSQL_PORT": self.mysql_port,
            "MYSQL_USER": self.mysql_user,
            "MYSQL_PASSWORD": self.mysql_password,
            "MYSQL_DB": self.mysql_db,
            "ocr_base_url": self.ocr_base_url,
            "OCR_BASE_URL": self.ocr_base_url,
            "OCR_RETRY_MAX": self.ocr_retry_max,
            "OCR_RETRY_SLEEP_SEC": self.ocr_retry_sleep_sec,
            "dify_api_key": self.dify_api_key,
            "DIFY_API_KEY": self.dify_api_key,
            "dify_base_url": self.dify_base_url,
            "DIFY_BASE_URL": self.dify_base_url,
            "dify_image_key": self.dify_image_key,
            "DIFY_IMAGE_KEY": self.dify_image_key,
            "dify_workflow_id": self.dify_workflow_id,
            "DIFY_WORKFLOW_ID": self.dify_workflow_id,
            "DIFY_RETRY_MAX": self.dify_retry_max,
            "DIFY_RETRY_SLEEP_SEC": self.dify_retry_sleep_sec,
            "feishu_app_id": self.feishu_app_id,
            "FEISHU_APP_ID": self.feishu_app_id,
            "feishu_app_secret": self.feishu_app_secret,
            "FEISHU_APP_SECRET": self.feishu_app_secret,
            "feishu_app_token": self.feishu_app_token,
            "FEISHU_APP_TOKEN": self.feishu_app_token,
            "bitable_app_token": self.feishu_app_token,
            "feishu_table_id": self.feishu_table_id,
            "FEISHU_TABLE_ID": self.feishu_table_id,
            "bitable_table_id": self.feishu_table_id,
            "FEISHU_SYNC_MODE": self.feishu_sync_mode,
            "SMTP_HOST": self.smtp_host,
            "SMTP_PORT": self.smtp_port,
            "SMTP_USER": self.smtp_user,
            "SMTP_PASS": self.smtp_pass,
            "SMTP_FROM_NAME": self.smtp_from_name,
            "SMTP_FROM_EMAIL": self.smtp_from_email,
            "SMTP_USE_TLS": self.smtp_use_tls,
            "SMTP_USE_SSL": self.smtp_use_ssl,
            "ALERT_FALLBACK_TO": self.alert_fallback_to,
            "UI_PORT": self.ui_port,
            "ui_port": self.ui_port,
            "ANOMALY_FORM_BASE_URL": self.anomaly_form_base_url,
        }


def get_settings() -> ProductSettings:
    load_env()
    root = project_root()
    storage_dir = str((root / (_pick("APP_STORAGE_DIR", "storage") or "storage")).resolve())
    upload_dir = str((Path(storage_dir) / "uploads").resolve())
    processed_dir = str((Path(storage_dir) / "processed").resolve())
    Path(upload_dir).mkdir(parents=True, exist_ok=True)
    Path(processed_dir).mkdir(parents=True, exist_ok=True)

    return ProductSettings(
        app_name=_pick("APP_NAME", "Invoice Audit Platform") or "Invoice Audit Platform",
        app_env=_pick("APP_ENV", "local") or "local",
        app_secret_key=_pick("APP_SECRET_KEY", "change-me-in-production") or "change-me-in-production",
        api_host=_pick("APP_API_HOST", "0.0.0.0") or "0.0.0.0",
        api_port=int(_pick("APP_API_PORT", "8080") or "8080"),
        api_base_url=_pick("APP_API_BASE_URL", f"http://127.0.0.1:{_pick('APP_API_PORT', '8080') or '8080'}")
        or f"http://127.0.0.1:{_pick('APP_API_PORT', '8080') or '8080'}",
        worker_id=_pick("APP_WORKER_ID", "worker-1") or "worker-1",
        task_poll_interval_sec=float(_pick("TASK_POLL_INTERVAL_SEC", "2") or "2"),
        task_retry_limit=int(_pick("TASK_RETRY_LIMIT", "3") or "3"),
        storage_dir=storage_dir,
        upload_dir=upload_dir,
        processed_dir=processed_dir,
        auth_session_ttl_hours=int(_pick("AUTH_SESSION_TTL_HOURS", "12") or "12"),
        auto_review_confidence_threshold=float(
            _pick("AUTO_REVIEW_CONFIDENCE_THRESHOLD", "0.85") or "0.85"
        ),
        mysql_host=_pick("MYSQL_HOST", "127.0.0.1") or "127.0.0.1",
        mysql_port=int(_pick("MYSQL_PORT", "3307") or "3307"),
        mysql_user=_pick("MYSQL_USER", "invoice_app") or "invoice_app",
        mysql_password=_pick("MYSQL_PASSWORD", "invoice_app_password") or "invoice_app_password",
        mysql_db=_pick("MYSQL_DB", "enterprise_ai") or "enterprise_ai",
        ocr_base_url=_pick("OCR_BASE_URL", "http://127.0.0.1:8000") or "http://127.0.0.1:8000",
        ocr_retry_max=int(_pick("OCR_RETRY_MAX", "5") or "5"),
        ocr_retry_sleep_sec=float(_pick("OCR_RETRY_SLEEP_SEC", "2.0") or "2.0"),
        dify_api_key=_pick("DIFY_API_KEY", "") or "",
        dify_base_url=_pick("DIFY_BASE_URL", "https://api.dify.ai/v1") or "https://api.dify.ai/v1",
        dify_image_key=_pick("DIFY_IMAGE_KEY", "invoice") or "invoice",
        dify_workflow_id=_pick("DIFY_WORKFLOW_ID", "") or "",
        dify_retry_max=int(_pick("DIFY_RETRY_MAX", "3") or "3"),
        dify_retry_sleep_sec=float(_pick("DIFY_RETRY_SLEEP_SEC", "2.0") or "2.0"),
        feishu_app_id=_pick("FEISHU_APP_ID", "") or "",
        feishu_app_secret=_pick("FEISHU_APP_SECRET", "") or "",
        feishu_app_token=_pick("FEISHU_APP_TOKEN", "") or "",
        feishu_table_id=_pick("FEISHU_TABLE_ID", "") or "",
        feishu_sync_mode=(_pick("FEISHU_SYNC_MODE", "off") or "off").lower(),
        smtp_host=_pick("SMTP_HOST", "") or "",
        smtp_port=int(_pick("SMTP_PORT", "1025") or "1025"),
        smtp_user=_pick("SMTP_USER", "") or "",
        smtp_pass=_pick("SMTP_PASS", "") or "",
        smtp_from_name=_pick("SMTP_FROM_NAME", "AI Invoice Audit Assistant") or "AI Invoice Audit Assistant",
        smtp_from_email=_pick("SMTP_FROM_EMAIL", "noreply@invoice-audit.local") or "noreply@invoice-audit.local",
        smtp_use_tls=_pick_bool("SMTP_USE_TLS", False),
        smtp_use_ssl=_pick_bool("SMTP_USE_SSL", False),
        alert_fallback_to=_pick("ALERT_FALLBACK_TO", "finance-demo@local.test") or "finance-demo@local.test",
        ui_port=int(_pick("UI_PORT", "8517") or "8517"),
        anomaly_form_base_url=_pick(
            "ANOMALY_FORM_BASE_URL",
            f"http://127.0.0.1:{_pick('UI_PORT', '8517') or '8517'}/?view=review",
        )
        or f"http://127.0.0.1:{_pick('UI_PORT', '8517') or '8517'}/?view=review",
        admin_username=_pick("APP_ADMIN_USERNAME", "admin") or "admin",
        admin_password=_pick("APP_ADMIN_PASSWORD", "admin123456") or "admin123456",
        operator_username=_pick("APP_OPERATOR_USERNAME", "operator") or "operator",
        operator_password=_pick("APP_OPERATOR_PASSWORD", "operator123456") or "operator123456",
        reviewer_username=_pick("APP_REVIEWER_USERNAME", "reviewer") or "reviewer",
        reviewer_password=_pick("APP_REVIEWER_PASSWORD", "reviewer123456") or "reviewer123456",
    )
