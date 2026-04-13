import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from dotenv import load_dotenv


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_env(override: bool = False) -> Optional[Path]:
    candidates = [
        project_root() / ".env",
        Path(__file__).with_name(".env"),
    ]
    for candidate in candidates:
        if candidate.exists():
            load_dotenv(candidate, override=override)
            return candidate
    return None


def _clean_env_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
    return text


def _env_pick(keys: Iterable[str], default: Optional[str] = None) -> Optional[str]:
    for key in keys:
        value = _clean_env_value(os.getenv(key))
        if value not in (None, ""):
            return value
    return default


def _resolve_path(value: str, root: Path) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return str(path.resolve())


@dataclass
class MySQLCfg:
    host: str
    port: int
    user: str
    password: str
    db: str


@dataclass
class OcrCfg:
    base_url: str
    retry_max: int
    retry_sleep: float


@dataclass
class DifyCfg:
    api_key: str
    base_url: str
    image_key: str
    workflow_id: str
    retry_max: int
    retry_sleep: float


@dataclass
class FeishuCfg:
    app_id: str
    app_secret: str
    bitable_app_token: str
    bitable_table_id: str
    sync_mode: str
    retry_worker_enabled: bool
    retry_interval_sec: int
    retry_mode: str
    retry_batch_limit: int


@dataclass
class EmailCfg:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    from_name: str
    from_email: str
    use_tls: bool
    use_ssl: bool
    alert_fallback_to: str


@dataclass
class AppCfg:
    invoices_dir: str
    purchase_no: str
    ui_port: int
    mysql: MySQLCfg
    ocr: OcrCfg
    dify: DifyCfg
    feishu: FeishuCfg
    email: EmailCfg
    anomaly_form_base_url: str

    def as_flat_dict(self) -> Dict[str, Any]:
        return {
            "invoices_dir": self.invoices_dir,
            "purchase_no": self.purchase_no,
            "PO_NO": self.purchase_no,
            "PURCHASE_NO": self.purchase_no,
            "ui_port": self.ui_port,
            "UI_PORT": self.ui_port,
            "ocr_base_url": self.ocr.base_url,
            "OCR_BASE_URL": self.ocr.base_url,
            "OCR_RETRY_MAX": self.ocr.retry_max,
            "OCR_RETRY_SLEEP_SEC": self.ocr.retry_sleep,
            "dify_api_key": self.dify.api_key,
            "DIFY_API_KEY": self.dify.api_key,
            "dify_base_url": self.dify.base_url,
            "DIFY_BASE_URL": self.dify.base_url,
            "dify_image_key": self.dify.image_key,
            "DIFY_IMAGE_KEY": self.dify.image_key,
            "dify_workflow_id": self.dify.workflow_id,
            "DIFY_WORKFLOW_ID": self.dify.workflow_id,
            "DIFY_RETRY_MAX": self.dify.retry_max,
            "DIFY_RETRY_SLEEP_SEC": self.dify.retry_sleep,
            "mysql_host": self.mysql.host,
            "MYSQL_HOST": self.mysql.host,
            "mysql_port": self.mysql.port,
            "MYSQL_PORT": self.mysql.port,
            "mysql_user": self.mysql.user,
            "MYSQL_USER": self.mysql.user,
            "mysql_password": self.mysql.password,
            "MYSQL_PASSWORD": self.mysql.password,
            "mysql_db": self.mysql.db,
            "MYSQL_DB": self.mysql.db,
            "MYSQL_DATABASE": self.mysql.db,
            "feishu_app_id": self.feishu.app_id,
            "FEISHU_APP_ID": self.feishu.app_id,
            "feishu_app_secret": self.feishu.app_secret,
            "FEISHU_APP_SECRET": self.feishu.app_secret,
            "feishu_app_token": self.feishu.bitable_app_token,
            "FEISHU_APP_TOKEN": self.feishu.bitable_app_token,
            "bitable_app_token": self.feishu.bitable_app_token,
            "feishu_table_id": self.feishu.bitable_table_id,
            "FEISHU_TABLE_ID": self.feishu.bitable_table_id,
            "bitable_table_id": self.feishu.bitable_table_id,
            "FEISHU_SYNC_MODE": self.feishu.sync_mode,
            "FEISHU_RETRY_WORKER_ENABLED": self.feishu.retry_worker_enabled,
            "FEISHU_RETRY_INTERVAL_SEC": self.feishu.retry_interval_sec,
            "FEISHU_RETRY_MODE": self.feishu.retry_mode,
            "FEISHU_RETRY_BATCH_LIMIT": self.feishu.retry_batch_limit,
            "SMTP_HOST": self.email.smtp_host,
            "SMTP_PORT": self.email.smtp_port,
            "SMTP_USER": self.email.smtp_user,
            "SMTP_PASS": self.email.smtp_pass,
            "SMTP_FROM_NAME": self.email.from_name,
            "SMTP_FROM_EMAIL": self.email.from_email,
            "ALERT_FALLBACK_TO": self.email.alert_fallback_to,
            "SMTP_USE_TLS": self.email.use_tls,
            "SMTP_USE_SSL": self.email.use_ssl,
            "ANOMALY_FORM_BASE_URL": self.anomaly_form_base_url,
        }


def load_config() -> AppCfg:
    load_env()
    root = project_root()

    invoices_dir = _resolve_path(
        _env_pick(["INVOICES_DIR", "IMAGE_FOLDER"], "./invoices") or "./invoices",
        root,
    )
    purchase_no = _env_pick(["PO_NO", "PURCHASE_NO"], "") or ""
    ui_port = int(_env_pick(["UI_PORT"], "8517") or "8517")

    mysql = MySQLCfg(
        host=_env_pick(["MYSQL_HOST"], "127.0.0.1") or "127.0.0.1",
        port=int(_env_pick(["MYSQL_PORT"], "3307") or "3307"),
        user=_env_pick(["MYSQL_USER"], "invoice_app") or "invoice_app",
        password=_env_pick(["MYSQL_PASSWORD"], "invoice_app_password") or "invoice_app_password",
        db=_env_pick(["MYSQL_DB", "MYSQL_DATABASE"], "enterprise_ai") or "enterprise_ai",
    )

    ocr = OcrCfg(
        base_url=_env_pick(["OCR_BASE_URL"], "http://127.0.0.1:8001") or "http://127.0.0.1:8001",
        retry_max=int(_env_pick(["OCR_RETRY_MAX"], "5") or "5"),
        retry_sleep=float(_env_pick(["OCR_RETRY_SLEEP_SEC"], "2.0") or "2.0"),
    )

    dify = DifyCfg(
        api_key=_env_pick(["DIFY_API_KEY"], "") or "",
        base_url=_env_pick(["DIFY_BASE_URL"], "https://api.dify.ai/v1") or "https://api.dify.ai/v1",
        image_key=_env_pick(["DIFY_IMAGE_KEY"], "invoice") or "invoice",
        workflow_id=_env_pick(["DIFY_WORKFLOW_ID"], "") or "",
        retry_max=int(_env_pick(["DIFY_RETRY_MAX"], "3") or "3"),
        retry_sleep=float(_env_pick(["DIFY_RETRY_SLEEP_SEC"], "2.0") or "2.0"),
    )

    feishu = FeishuCfg(
        app_id=_env_pick(["FEISHU_APP_ID"], "") or "",
        app_secret=_env_pick(["FEISHU_APP_SECRET"], "") or "",
        bitable_app_token=_env_pick(["FEISHU_APP_TOKEN", "BITABLE_APP_TOKEN"], "") or "",
        bitable_table_id=_env_pick(["FEISHU_TABLE_ID", "BITABLE_TABLE_ID"], "") or "",
        sync_mode=(_env_pick(["FEISHU_SYNC_MODE"], "off") or "off").lower(),
        retry_worker_enabled=(_env_pick(["FEISHU_RETRY_WORKER_ENABLED"], "False") or "False").lower() in ("true", "1", "yes"),
        retry_interval_sec=int(_env_pick(["FEISHU_RETRY_INTERVAL_SEC"], "300") or "300"),
        retry_mode=(_env_pick(["FEISHU_RETRY_MODE"], "failed") or "failed").lower(),
        retry_batch_limit=int(_env_pick(["FEISHU_RETRY_BATCH_LIMIT"], "20") or "20"),
    )

    use_tls = (_env_pick(["SMTP_USE_TLS"], "True") or "True").lower() in ("true", "1", "yes")
    use_ssl = (_env_pick(["SMTP_USE_SSL"], "False") or "False").lower() in ("true", "1", "yes")

    email = EmailCfg(
        smtp_host=_env_pick(["SMTP_HOST"], "") or "",
        smtp_port=int(_env_pick(["SMTP_PORT"], "1025") or "1025"),
        smtp_user=_env_pick(["SMTP_USER"], "") or "",
        smtp_pass=_env_pick(["SMTP_PASS"], "") or "",
        from_name=_env_pick(["SMTP_FROM_NAME", "MAIL_SENDER_NAME"], "AI Invoice Audit Assistant")
        or "AI Invoice Audit Assistant",
        from_email=_env_pick(
            ["SMTP_FROM_EMAIL", "MAIL_FROM_EMAIL", "SMTP_USER"],
            "noreply@invoice-audit.local",
        )
        or "noreply@invoice-audit.local",
        use_tls=use_tls,
        use_ssl=use_ssl,
        alert_fallback_to=_env_pick(
            ["ALERT_FALLBACK_TO", "SMTP_USER"],
            "finance-demo@local.test",
        )
        or "finance-demo@local.test",
    )

    return AppCfg(
        invoices_dir=invoices_dir,
        purchase_no=purchase_no,
        ui_port=ui_port,
        mysql=mysql,
        ocr=ocr,
        dify=dify,
        feishu=feishu,
        email=email,
        anomaly_form_base_url=_env_pick(
            ["ANOMALY_FORM_BASE_URL"],
            f"http://127.0.0.1:{ui_port}/?view=anomaly_form",
        )
        or f"http://127.0.0.1:{ui_port}/?view=anomaly_form",
    )


def load_flat_config() -> Dict[str, Any]:
    return load_config().as_flat_dict()
