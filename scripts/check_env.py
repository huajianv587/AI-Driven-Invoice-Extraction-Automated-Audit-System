from __future__ import annotations

import socket
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_config, load_flat_config


INT_KEYS = {
    "MYSQL_PORT",
    "OCR_RETRY_MAX",
    "DIFY_RETRY_MAX",
    "SMTP_PORT",
    "UI_PORT",
    "MAILPIT_SMTP_PORT",
    "MAILPIT_WEB_PORT",
    "FEISHU_RETRY_INTERVAL_SEC",
    "FEISHU_RETRY_BATCH_LIMIT",
}

FLOAT_KEYS = {
    "OCR_RETRY_SLEEP_SEC",
    "DIFY_RETRY_SLEEP_SEC",
}

URL_KEYS = {
    "OCR_BASE_URL",
    "DIFY_BASE_URL",
    "ANOMALY_FORM_BASE_URL",
}

PLACEHOLDER_MARKERS = (
    "你的",
    "请填写",
    "changeme",
    "your_",
    "your-",
    "<your",
)

OCR_OPENAPI_TIMEOUT_SEC = 2
DEMO_EMAIL_DOMAINS = {"local.test", "example.com", "example.org", "example.net"}
FEISHU_RETRY_MODES = {"pending", "failed", "recoverable", "all"}


def read_env_file(env_path: Path) -> Tuple[Dict[str, str], Dict[str, List[Tuple[int, str]]]]:
    values: Dict[str, str] = {}
    occurrences: Dict[str, List[Tuple[int, str]]] = defaultdict(list)

    if not env_path.exists():
        raise FileNotFoundError(f".env not found: {env_path}")

    for line_no, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
        occurrences[key].append((line_no, value))

    return values, occurrences


def is_placeholder(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    lower = text.lower()
    return any(lower.startswith(marker) or marker in lower for marker in PLACEHOLDER_MARKERS)


def mask_value(value: str) -> str:
    if value == "":
        return "EMPTY"
    if len(value) <= 8:
        return f"{value[:2]}... (len={len(value)})"
    return f"{value[:4]}...{value[-4:]} (len={len(value)})"


def validate_number(key: str, value: str, errors: List[str]) -> None:
    if value == "":
        return
    try:
        if key in INT_KEYS:
            int(value)
        elif key in FLOAT_KEYS:
            float(value)
    except Exception:
        errors.append(f"{key} must be numeric, got {value!r}.")


def validate_url(key: str, value: str, errors: List[str]) -> None:
    if not value:
        return
    parsed = urlparse(value if "://" in value else f"http://{value}")
    if not parsed.scheme or not parsed.netloc:
        errors.append(f"{key} is not a valid URL: {value!r}.")


def is_local_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}


def is_demo_email(email: str) -> bool:
    text = (email or "").strip().lower()
    if not text or "@" not in text:
        return False
    domain = text.rsplit("@", 1)[-1]
    return domain in DEMO_EMAIL_DOMAINS or domain.endswith(".local.test")


def is_port_open(host: str, port: int) -> bool:
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.5)
        return sock.connect_ex((probe_host, port)) == 0


def check_ocr_endpoint(ocr_base_url: str, errors: List[str], infos: List[str], warnings: List[str]) -> None:
    if not ocr_base_url:
        return

    parsed = urlparse(ocr_base_url if "://" in ocr_base_url else f"http://{ocr_base_url}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    if not is_local_host(host):
        infos.append(f"OCR_BASE_URL points to remote host {host}:{port}; skipped local port conflict check.")
        return

    if not is_port_open(host, port):
        infos.append(f"OCR port {host}:{port} is available.")
        return

    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    openapi_url = f"{parsed.scheme or 'http'}://{probe_host}:{port}/openapi.json"

    try:
        resp = requests.get(openapi_url, timeout=OCR_OPENAPI_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        title = ((data.get("info") or {}).get("title") or "").strip()
        paths = data.get("paths") or {}
        if "/ocr" in paths:
            infos.append(f"OCR service already responds on {probe_host}:{port}.")
            return

        detail = f"openapi title={title!r}" if title else "openapi.json exists but /ocr route is missing"
        errors.append(
            f"OCR_BASE_URL points to {probe_host}:{port}, but that port is occupied by another HTTP service ({detail})."
        )
    except requests.RequestException as exc:
        warnings.append(
            f"OCR port {probe_host}:{port} is already listening, but its OpenAPI probe failed: {exc}."
        )


def validate_optional_integrations(env_values: Dict[str, str], errors: List[str], warnings: List[str], infos: List[str]) -> None:
    dify_key = env_values.get("DIFY_API_KEY", "").strip()
    dify_workflow_id = env_values.get("DIFY_WORKFLOW_ID", "").strip()
    if dify_key and not dify_workflow_id:
        errors.append("DIFY_API_KEY is set but DIFY_WORKFLOW_ID is empty.")
    elif dify_workflow_id and not dify_key:
        errors.append("DIFY_WORKFLOW_ID is set but DIFY_API_KEY is empty.")
    elif dify_key and dify_workflow_id:
        infos.append("Dify extraction is configured.")
    else:
        warnings.append("Dify extraction is disabled because DIFY_API_KEY / DIFY_WORKFLOW_ID are empty.")

    feishu_fields = [
        env_values.get("FEISHU_APP_ID", "").strip(),
        env_values.get("FEISHU_APP_SECRET", "").strip(),
        env_values.get("FEISHU_APP_TOKEN", "").strip(),
        env_values.get("FEISHU_TABLE_ID", "").strip(),
    ]
    feishu_sync_mode = env_values.get("FEISHU_SYNC_MODE", "").strip().lower() or "off"
    retry_worker_enabled = env_values.get("FEISHU_RETRY_WORKER_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    retry_mode = env_values.get("FEISHU_RETRY_MODE", "").strip().lower() or "failed"
    retry_interval = env_values.get("FEISHU_RETRY_INTERVAL_SEC", "").strip()
    retry_batch_limit = env_values.get("FEISHU_RETRY_BATCH_LIMIT", "").strip()
    if any(feishu_fields) and not all(feishu_fields):
        warnings.append("Feishu config is partially filled; inline sync may fail.")
    elif all(feishu_fields):
        infos.append(f"Feishu sync is configured (mode={feishu_sync_mode}).")
    if retry_mode not in FEISHU_RETRY_MODES:
        errors.append(
            "FEISHU_RETRY_MODE must be one of "
            f"{', '.join(sorted(FEISHU_RETRY_MODES))}, got {retry_mode!r}."
        )
    if retry_interval:
        try:
            if int(retry_interval) <= 0:
                errors.append("FEISHU_RETRY_INTERVAL_SEC must be greater than 0.")
        except Exception:
            pass
    if retry_batch_limit:
        try:
            if int(retry_batch_limit) <= 0:
                errors.append("FEISHU_RETRY_BATCH_LIMIT must be greater than 0.")
        except Exception:
            pass
    if retry_worker_enabled:
        infos.append(
            "Feishu retry worker is enabled "
            f"(mode={retry_mode}, interval={retry_interval or '300'}s, limit={retry_batch_limit or '20'})."
        )
        if not all(feishu_fields):
            warnings.append("FEISHU_RETRY_WORKER_ENABLED is on, but Feishu credentials are incomplete.")
        if feishu_sync_mode == "off":
            warnings.append(
                "FEISHU_RETRY_WORKER_ENABLED is on while FEISHU_SYNC_MODE=off. "
                "Recovery can replay failed rows, but new invoices will not auto-sync inline."
            )

    smtp_host = env_values.get("SMTP_HOST", "").strip()
    smtp_user = env_values.get("SMTP_USER", "").strip()
    smtp_pass = env_values.get("SMTP_PASS", "").strip()
    if smtp_host in {"127.0.0.1", "localhost"} and (smtp_user or smtp_pass):
        warnings.append("SMTP_HOST is local, but SMTP_USER / SMTP_PASS are set. Local Mailpit usually does not need SMTP AUTH.")
    if smtp_host in {"127.0.0.1", "localhost"}:
        warnings.append("SMTP currently points to local Mailpit. Alerts will appear in http://127.0.0.1:8025 and will not reach external inboxes.")


def inspect_alert_recipients(warnings: List[str], infos: List[str]) -> None:
    try:
        cfg = load_config()
    except Exception:
        return

    try:
        import pymysql
    except Exception as exc:
        infos.append(f"Skipped purchase-order recipient inspection because PyMySQL is unavailable: {exc}")
        return

    try:
        conn = pymysql.connect(
            host=cfg.mysql.host,
            port=cfg.mysql.port,
            user=cfg.mysql.user,
            password=cfg.mysql.password,
            database=cfg.mysql.db,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=2,
            read_timeout=2,
            write_timeout=2,
        )
    except Exception as exc:
        infos.append(f"Skipped purchase-order recipient inspection because MySQL is unavailable: {exc}")
        return

    try:
        with conn.cursor() as cur:
            purchase_no = (cfg.purchase_no or "").strip()
            if purchase_no:
                cur.execute(
                    """
                    SELECT purchase_no, purchaser_email, leader_email
                    FROM purchase_orders
                    WHERE purchase_no=%s
                    LIMIT 1
                    """,
                    (purchase_no,),
                )
                rows = [cur.fetchone()] if cur.rowcount else []
            else:
                cur.execute(
                    """
                    SELECT purchase_no, purchaser_email, leader_email
                    FROM purchase_orders
                    ORDER BY id DESC
                    LIMIT 5
                    """
                )
                rows = cur.fetchall()
    except Exception as exc:
        infos.append(f"Skipped purchase-order recipient inspection because the query failed: {exc}")
        return
    finally:
        conn.close()

    rows = [row for row in rows if row]
    if not rows:
        infos.append("No purchase_orders rows were found for recipient inspection.")
        return

    demo_rows = []
    for row in rows:
        purchaser_email = (row.get("purchaser_email") or "").strip()
        leader_email = (row.get("leader_email") or "").strip()
        if is_demo_email(purchaser_email) or is_demo_email(leader_email):
            demo_rows.append(
                f"{row.get('purchase_no')}: purchaser_email={purchaser_email or 'EMPTY'}, leader_email={leader_email or 'EMPTY'}"
            )

    if demo_rows:
        preview = "; ".join(demo_rows[:3])
        warnings.append(
            "Purchase-order recipients still look like demo addresses. "
            f"Current rows: {preview}. Risk alerts will go there unless you update purchase_orders."
        )


def main() -> int:
    env_path = ROOT / ".env"
    errors: List[str] = []
    warnings: List[str] = []
    infos: List[str] = []

    try:
        env_values, occurrences = read_env_file(env_path)
    except Exception as exc:
        print(f"[error] {exc}")
        return 1

    infos.append(f"Using .env: {env_path}")

    for key, hits in sorted(occurrences.items()):
        if len(hits) > 1:
            line_list = ", ".join(str(line_no) for line_no, _ in hits)
            errors.append(f"Duplicate key {key} found at lines {line_list}. Later values override earlier ones.")

    for key, value in sorted(env_values.items()):
        if is_placeholder(value):
            errors.append(f"{key} still looks like a placeholder value: {mask_value(value)}.")
        if key in INT_KEYS or key in FLOAT_KEYS:
            validate_number(key, value, errors)
        if key in URL_KEYS:
            validate_url(key, value, errors)

    validate_optional_integrations(env_values, errors, warnings, infos)
    check_ocr_endpoint(env_values.get("OCR_BASE_URL", ""), errors, infos, warnings)
    inspect_alert_recipients(warnings, infos)

    try:
        load_flat_config()
        infos.append("src.config.load_flat_config() succeeded.")
    except Exception as exc:
        errors.append(f"load_flat_config() failed: {exc}")

    for msg in infos:
        print(f"[ok] {msg}")
    for msg in warnings:
        print(f"[warn] {msg}")
    for msg in errors:
        print(f"[error] {msg}")

    if errors:
        print(f"[summary] {len(errors)} error(s), {len(warnings)} warning(s).")
        return 1

    print(f"[summary] Environment validation passed with {len(warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
