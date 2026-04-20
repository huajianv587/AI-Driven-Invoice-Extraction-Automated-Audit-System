from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymysql
import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config
from src.services.feishu_bitable_client import FeishuBitableClient
from src.services.imap_test_client import IMAPInboxChecker
from scripts.deep_product_regression import (
    PYTHON,
    align_demo_purchase_order_recipients,
    assert_true,
    ensure_ocr_process,
    latest_email_event,
    process_invoice,
    reset_demo_state,
    resolve_invoice_path,
    run_cmd,
    with_overrides,
)
from scripts.guard_deep_regression import validate_deep_regression_safety


ARTIFACTS = ROOT / "artifacts" / "required-mode"
DEFAULT_FIXTURE = "\u53d1\u79684.jpg"
CONNECTOR_NAMES = ("OCR", "Dify", "Feishu", "SMTP")


def report_path() -> Path:
    raw = str(os.getenv("REQUIRED_MODE_REPORT_PATH") or "").strip()
    if raw:
        return Path(raw).resolve()
    return (ARTIFACTS / "latest.json").resolve()


def required_cfg(cfg: Dict[str, Any], **overrides: Any) -> Dict[str, Any]:
    merged = with_overrides(
        cfg,
        DIFY_REQUIRED=True,
        dify_required=True,
        FEISHU_SYNC_REQUIRED=True,
        feishu_sync_required=True,
        FEISHU_SYNC_MODE="inline",
        EMAIL_ALERT_REQUIRED=True,
        email_alert_required=True,
    )
    merged.update(overrides)
    return merged


def required_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["DIFY_REQUIRED"] = "True"
    env["FEISHU_SYNC_REQUIRED"] = "True"
    env["FEISHU_SYNC_MODE"] = "inline"
    env["EMAIL_ALERT_REQUIRED"] = "True"
    return env


def imap_checker_from_env() -> IMAPInboxChecker:
    host = str(os.getenv("TEST_IMAP_HOST") or "").strip()
    port = int(str(os.getenv("TEST_IMAP_PORT") or "993").strip() or "993")
    user = str(os.getenv("TEST_IMAP_USER") or "").strip()
    password = str(os.getenv("TEST_IMAP_PASS") or "")
    mailbox = str(os.getenv("TEST_IMAP_MAILBOX") or "INBOX").strip() or "INBOX"
    use_ssl = str(os.getenv("TEST_IMAP_USE_SSL") or "True").strip().lower() in {"1", "true", "yes", "on"}
    missing = [name for name, value in (
        ("TEST_IMAP_HOST", host),
        ("TEST_IMAP_USER", user),
        ("TEST_IMAP_PASS", password),
    ) if not value]
    if missing:
        raise RuntimeError(f"Required IMAP test settings are missing: {', '.join(missing)}")
    return IMAPInboxChecker(
        host=host,
        port=port,
        username=user,
        password=password,
        use_ssl=use_ssl,
        mailbox=mailbox,
    )


def mysql_connection(cfg: Dict[str, Any]):
    return pymysql.connect(
        host=str(cfg["MYSQL_HOST"]),
        port=int(cfg["MYSQL_PORT"]),
        user=str(cfg["MYSQL_USER"]),
        password=str(cfg["MYSQL_PASSWORD"]),
        database=str(cfg["MYSQL_DB"]),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def source_state(cfg: Dict[str, Any], file_name: str) -> Dict[str, Any]:
    source_path = str(resolve_invoice_path(file_name))
    conn = mysql_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS source_count
                FROM invoices
                WHERE source_file_path=%s
                """,
                (source_path,),
            )
            count_row = cur.fetchone() or {}
            cur.execute(
                """
                SELECT id, invoice_code, invoice_number, purchase_order_no, expected_amount,
                       amount_diff, risk_flag, invoice_status, notify_personal_status,
                       notify_leader_status, unique_hash, source_file_path
                FROM invoices
                WHERE source_file_path=%s
                ORDER BY id DESC
                LIMIT 1
                """,
                (source_path,),
            )
            invoice = cur.fetchone()
            events: List[Dict[str, Any]] = []
            items: List[Dict[str, Any]] = []
            sync: Dict[str, Any] | None = None
            if invoice:
                cur.execute(
                    """
                    SELECT item_name, item_spec, item_quantity, item_unit_price, item_amount, tax_rate, tax_amount
                    FROM invoice_items
                    WHERE invoice_id=%s
                    ORDER BY id ASC
                    """,
                    (invoice["id"],),
                )
                items = list(cur.fetchall() or [])
                cur.execute(
                    """
                    SELECT event_type, event_status, payload
                    FROM invoice_events
                    WHERE invoice_id=%s
                    ORDER BY id ASC
                    """,
                    (invoice["id"],),
                )
                events = list(cur.fetchall() or [])
                cur.execute(
                    """
                    SELECT feishu_record_id, synced_at, sync_error
                    FROM invoice_feishu_sync
                    WHERE invoice_id=%s
                    LIMIT 1
                    """,
                    (invoice["id"],),
                )
                sync = cur.fetchone()
    finally:
        conn.close()

    for event in events:
        payload = event.get("payload")
        if isinstance(payload, str):
            try:
                event["payload"] = json.loads(payload)
            except Exception:
                pass

    return {
        "invoice_count_for_source": int(count_row.get("source_count") or 0),
        "invoice": invoice,
        "items": items,
        "events": events,
        "sync": sync or {},
    }


def run_invoice_capture(file_name: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    try:
        summary = process_invoice(file_name, cfg)
        state = source_state(cfg, file_name)
        return {
            "raised": False,
            "error": None,
            "result": summary.get("result"),
            **state,
        }
    except Exception as exc:
        state = source_state(cfg, file_name)
        return {
            "raised": True,
            "error": f"{type(exc).__name__}: {exc}",
            "result": None,
            **state,
        }


def api_is_running(base_url: str) -> bool:
    try:
        response = requests.get(f"{base_url}/api/health", timeout=3)
        return response.ok
    except Exception:
        return False


def start_api_process(env: Dict[str, str]) -> tuple[subprocess.Popen, Any, Path]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    log_path = ARTIFACTS / "api.log"
    log_file = log_path.open("w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [PYTHON, "api_server.py"],
        cwd=str(ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, log_file, log_path


def stop_process(proc: Optional[subprocess.Popen], log_file: Any = None) -> None:
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    if log_file is not None:
        try:
            log_file.close()
        except Exception:
            pass


def wait_api_readiness(base_url: str, proc: subprocess.Popen, log_path: Path, timeout_sec: int = 120) -> Dict[str, Any]:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"API process exited early. See {log_path}.")
        try:
            response = requests.get(f"{base_url}/api/readiness", timeout=5)
            payload = response.json()
            if response.ok:
                return payload
            last_error = json.dumps(payload, ensure_ascii=False)
        except Exception as exc:
            last_error = repr(exc)
        time.sleep(1)
    raise RuntimeError(f"FastAPI readiness did not become ready: {last_error}")


def login_admin(base_url: str, cfg: Dict[str, Any]) -> str:
    response = requests.post(
        f"{base_url}/api/auth/login",
        json={
            "email": str(cfg["AUTH_BOOTSTRAP_ADMIN_EMAIL"]),
            "password": str(cfg["AUTH_BOOTSTRAP_ADMIN_PASSWORD"]),
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["access_token"])


def refresh_connectors(base_url: str, token: str) -> List[Dict[str, Any]]:
    response = requests.get(
        f"{base_url}/api/ops/connectors?refresh=true",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    response.raise_for_status()
    rows = list(response.json() or [])
    names = {row.get("name") for row in rows}
    missing = [name for name in CONNECTOR_NAMES if name not in names]
    if missing:
        raise RuntimeError(f"Connector refresh missed rows: {', '.join(missing)}")
    bad = [row for row in rows if row.get("name") in CONNECTOR_NAMES and row.get("status") != "OK"]
    if bad:
        raise RuntimeError(f"Connector refresh is not healthy: {json.dumps(bad, ensure_ascii=False)}")
    return rows


def feishu_client(cfg: Dict[str, Any]) -> FeishuBitableClient:
    return FeishuBitableClient(
        app_id=str(cfg["FEISHU_APP_ID"]),
        app_secret=str(cfg["FEISHU_APP_SECRET"]),
        app_token=str(cfg["FEISHU_APP_TOKEN"]),
        table_id=str(cfg["FEISHU_TABLE_ID"]),
    )


def scenario_marker(run_id: str, suffix: str) -> str:
    return f"REQUIRED-{run_id}-{suffix}".upper()


def scenario_required_success(cfg: Dict[str, Any], inbox: IMAPInboxChecker, run_id: str) -> Dict[str, Any]:
    file_name = DEFAULT_FIXTURE
    marker = scenario_marker(run_id, "SUCCESS")
    scenario_cfg = with_overrides(cfg, WEB_DEEP_EXTERNAL_PREFIX=marker)
    reset_demo_state()
    align_demo_purchase_order_recipients(cfg)
    started_at = time.time()

    first = run_invoice_capture(file_name, scenario_cfg)
    assert_true(not first["raised"], f"Required success scenario raised unexpectedly: {first['error']}")
    first_result = first["result"] or {}
    first_invoice = first["invoice"] or {}
    first_events = first["events"] or []
    first_sync = first["sync"] or {}
    first_email = latest_email_event(first_events) or {}
    first_payload = first_email.get("payload") if isinstance(first_email.get("payload"), dict) else {}
    unique_hash = str(first_result.get("unique_hash") or first_invoice.get("unique_hash") or "").strip()

    assert_true(first_result.get("action") == "inserted", f"Expected inserted result, got {first_result}")
    assert_true(first["invoice_count_for_source"] == 1, f"Expected one inserted invoice, got {first['invoice_count_for_source']}")
    assert_true(first_email.get("event_status") == "SENT", f"Expected EMAIL_ALERT/SENT, got {first_email}")
    assert_true(unique_hash, f"Required success run did not produce a unique hash: {first}")

    imap_message = inbox.wait_for_message(
        after_epoch=started_at,
        subject_contains=marker,
        body_contains=unique_hash,
        timeout_sec=90,
        poll_interval_sec=5,
        limit=30,
    )
    assert_true(
        str(first_payload.get("subject") or "") == imap_message.subject,
        f"IMAP subject mismatch: payload={first_payload} imap={imap_message.subject!r}",
    )
    assert_true(unique_hash in imap_message.body, f"IMAP body is missing unique hash {unique_hash!r}.")

    client = feishu_client(cfg)
    token = client.get_tenant_token()
    assert_true(bool(token), "Feishu token acquisition failed in required success scenario.")
    record_id = str(first_sync.get("feishu_record_id") or "").strip()
    assert_true(bool(record_id), f"Required success scenario did not persist a Feishu record id: {first_sync}")
    ok, remote = client.get_record(token, record_id)
    assert_true(ok, f"Required success scenario could not read back Feishu record {record_id}: {remote}")
    remote_fields = (((remote or {}).get("data") or {}).get("record") or {}).get("fields") or {}
    remote_unique_hash = str(remote_fields.get("unique_hash") or "").strip()
    assert_true(remote_unique_hash == unique_hash, f"Feishu record unique_hash mismatch: {remote_fields}")

    duplicate = run_invoice_capture(file_name, scenario_cfg)
    assert_true(not duplicate["raised"], f"Duplicate required run raised unexpectedly: {duplicate['error']}")
    duplicate_result = duplicate["result"] or {}
    duplicate_sync = duplicate["sync"] or {}
    duplicate_messages = inbox.find_messages(
        after_epoch=started_at,
        subject_contains=marker,
        body_contains=unique_hash,
        limit=30,
    )
    assert_true(duplicate_result.get("action") == "skipped", f"Expected duplicate skip, got {duplicate_result}")
    assert_true(len(duplicate_messages) == 1, f"Duplicate required run sent extra email(s): {len(duplicate_messages)}")
    assert_true(
        str(duplicate_sync.get("feishu_record_id") or "") == record_id,
        f"Duplicate required run changed Feishu record id: {duplicate_sync}",
    )

    return {
        "scenario": "required_success",
        "marker": marker,
        "first": first_result,
        "duplicate": duplicate_result,
        "invoice_id": first_invoice.get("id"),
        "invoice_count_for_source": duplicate["invoice_count_for_source"],
        "email": {
            "event_status": first_email.get("event_status"),
            "subject": first_payload.get("subject"),
            "imap_subject": imap_message.subject,
            "message_count": len(duplicate_messages),
            "body_has_unique_hash": unique_hash in imap_message.body,
        },
        "feishu": {
            "record_id": record_id,
            "remote_unique_hash": remote_unique_hash,
            "record_id_unchanged": str(duplicate_sync.get("feishu_record_id") or "") == record_id,
        },
    }


def scenario_required_dify_failure(cfg: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    file_name = DEFAULT_FIXTURE
    marker = scenario_marker(run_id, "DIFYFAIL")
    reset_demo_state()
    align_demo_purchase_order_recipients(cfg)
    failing_cfg = with_overrides(
        cfg,
        WEB_DEEP_EXTERNAL_PREFIX=marker,
        DIFY_BASE_URL="http://127.0.0.1:9/v1",
        dify_base_url="http://127.0.0.1:9/v1",
        DIFY_RETRY_MAX=1,
    )

    result = run_invoice_capture(file_name, failing_cfg)
    assert_true(result["raised"], "Required Dify failure scenario did not raise.")
    assert_true(
        result["invoice_count_for_source"] == 0,
        f"Required Dify failure inserted invoice rows unexpectedly: {result['invoice_count_for_source']}",
    )

    return {
        "scenario": "required_dify_failure",
        "marker": marker,
        "error": result["error"],
        "invoice_count_for_source": result["invoice_count_for_source"],
    }


def scenario_required_smtp_failure(cfg: Dict[str, Any], inbox: IMAPInboxChecker, run_id: str) -> Dict[str, Any]:
    file_name = DEFAULT_FIXTURE
    marker = scenario_marker(run_id, "SMTPFAIL")
    reset_demo_state()
    align_demo_purchase_order_recipients(cfg)
    started_at = time.time()
    failing_cfg = with_overrides(
        cfg,
        WEB_DEEP_EXTERNAL_PREFIX=marker,
        SMTP_PORT=1,
        SMTP_USE_TLS=False,
        SMTP_USE_SSL=False,
    )

    result = run_invoice_capture(file_name, failing_cfg)
    assert_true(result["raised"], "Required SMTP failure scenario did not raise.")
    invoice = result["invoice"] or {}
    events = result["events"] or []
    email_statuses = [event.get("event_status") for event in events if event.get("event_type") == "EMAIL_ALERT"]
    unique_hash = str((invoice or {}).get("unique_hash") or "").strip()
    time.sleep(3)
    imap_messages = inbox.find_messages(
        after_epoch=started_at,
        subject_contains=marker,
        body_contains=unique_hash,
        limit=20,
    )

    assert_true(bool(invoice), f"Required SMTP failure did not leave an invoice row: {result}")
    assert_true(email_statuses == ["FAILED"], f"Expected EMAIL_ALERT/FAILED only, got {email_statuses}")
    assert_true(len(imap_messages) == 0, f"Required SMTP failure produced an unexpected inbox hit: {imap_messages}")

    return {
        "scenario": "required_smtp_failure",
        "marker": marker,
        "error": result["error"],
        "invoice_id": invoice.get("id"),
        "unique_hash": unique_hash,
        "email_statuses": email_statuses,
        "imap_message_count": len(imap_messages),
    }


def scenario_required_feishu_failure(cfg: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    file_name = DEFAULT_FIXTURE
    marker = scenario_marker(run_id, "FEISHUFAIL")
    reset_demo_state()
    align_demo_purchase_order_recipients(cfg)
    failing_cfg = with_overrides(
        cfg,
        WEB_DEEP_EXTERNAL_PREFIX=marker,
        FEISHU_APP_SECRET="invalid-required-smoke-secret",
        feishu_app_secret="invalid-required-smoke-secret",
    )

    result = run_invoice_capture(file_name, failing_cfg)
    assert_true(result["raised"], "Required Feishu failure scenario did not raise.")
    invoice = result["invoice"] or {}
    sync = result["sync"] or {}
    record_id = str(sync.get("feishu_record_id") or "").strip()
    sync_error = str(sync.get("sync_error") or "").strip()
    remote_record_readable = False

    if record_id:
        token = feishu_client(cfg).get_tenant_token()
        if token:
            ok, _ = feishu_client(cfg).get_record(token, record_id)
            remote_record_readable = ok

    assert_true(bool(invoice), f"Required Feishu failure did not leave an invoice row: {result}")
    assert_true(bool(sync_error), f"Required Feishu failure did not persist sync_error: {sync}")
    assert_true(not remote_record_readable, "Required Feishu failure left a readable remote record.")

    return {
        "scenario": "required_feishu_failure",
        "marker": marker,
        "error": result["error"],
        "invoice_id": invoice.get("id"),
        "record_id": record_id or None,
        "sync_error": sync_error,
        "remote_record_readable": remote_record_readable,
    }


def main() -> None:
    validate_deep_regression_safety()
    load_env(override=True)
    base_cfg = required_cfg(load_flat_config())
    current_run_id = uuid.uuid4().hex[:10]
    base_url = f"http://127.0.0.1:{int(base_cfg['API_PORT'])}"
    report = report_path()
    report.parent.mkdir(parents=True, exist_ok=True)
    inbox = imap_checker_from_env()

    if api_is_running(base_url):
        raise RuntimeError(
            f"API is already running on {base_url}. Stop it before required smoke so startup preflight can be verified."
        )

    run_cmd(["docker", "compose", "up", "-d", "mysql"])
    run_cmd([PYTHON, "scripts/apply_schema.py"])
    run_cmd([PYTHON, "scripts/check_env.py"])

    api_proc: Optional[subprocess.Popen] = None
    api_log = None
    ocr_proc = None

    try:
        ocr_proc = ensure_ocr_process(str(base_cfg["OCR_BASE_URL"]).rstrip("/"), timeout_sec=120)

        api_proc, api_log, api_log_path = start_api_process(required_env())
        readiness = wait_api_readiness(base_url, api_proc, api_log_path, timeout_sec=120)
        access_token = login_admin(base_url, base_cfg)
        connector_rows = refresh_connectors(base_url, access_token)
        stop_process(api_proc, api_log)
        api_proc = None
        api_log = None

        scenarios = [
            scenario_required_success(base_cfg, inbox, current_run_id),
            scenario_required_dify_failure(base_cfg, current_run_id),
            scenario_required_smtp_failure(base_cfg, inbox, current_run_id),
            scenario_required_feishu_failure(base_cfg, current_run_id),
        ]
        summary = {
            "ok": True,
            "mode": "required",
            "run_id": current_run_id,
            "fixture": DEFAULT_FIXTURE,
            "scenario_count": len(scenarios),
            "preflight": {
                "readiness": readiness,
                "connector_statuses": connector_rows,
            },
            "scenarios": scenarios,
        }
        report.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    finally:
        stop_process(api_proc, api_log)
        if ocr_proc is not None:
            try:
                ocr_proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
