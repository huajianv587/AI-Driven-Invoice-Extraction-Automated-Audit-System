from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from multiprocessing import get_context
from pathlib import Path
from queue import Empty
from typing import Any, Dict, List

import pymysql
import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config
from src.main import build_service
from src.services.ingestion_service import process_one_image


PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")
DEFAULT_PURCHASE_NO = "PO-DEMO-001"


def run_cmd(args: list[str]) -> None:
    subprocess.run(args, cwd=str(ROOT), check=True)


def wait_ocr(base_url: str, timeout_sec: int = 120) -> None:
    base_url = base_url.rstrip("/")
    deadline = time.time() + timeout_sec
    last_error = None

    while time.time() < deadline:
        try:
            resp = requests.get(f"{base_url}/openapi.json", timeout=5)
            resp.raise_for_status()
            paths = (resp.json() or {}).get("paths") or {}
            if "/ocr" in paths:
                return
            last_error = "missing /ocr route"
        except Exception as exc:
            last_error = exc
        time.sleep(2)

    raise RuntimeError(f"OCR endpoint not ready: {base_url} -> {last_error}")


def ensure_ocr_process(base_url: str, timeout_sec: int = 120):
    try:
        wait_ocr(base_url, timeout_sec=5)
        return None
    except Exception:
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        proc = subprocess.Popen(
            [PYTHON, "ocr_server.py"],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_ocr(base_url, timeout_sec=timeout_sec)
        return proc


def demo_recipient() -> str:
    recipient = os.getenv("ALERT_FALLBACK_TO", "").strip() or os.getenv("SMTP_FROM_EMAIL", "").strip() or os.getenv("SMTP_USER", "").strip()
    if not recipient:
        raise RuntimeError("Missing alert recipient in .env. Fill ALERT_FALLBACK_TO or SMTP_USER first.")
    return recipient


def demo_leader_email() -> str:
    return os.getenv("DEMO_LEADER_EMAIL", "").strip()


def current_cfg() -> Dict[str, Any]:
    load_env(override=True)
    return load_flat_config()


def align_demo_purchase_order_recipients(cfg: Dict[str, Any]) -> Dict[str, Any]:
    conn = pymysql.connect(
        host=str(cfg["MYSQL_HOST"]),
        port=int(cfg["MYSQL_PORT"]),
        user=str(cfg["MYSQL_USER"]),
        password=str(cfg["MYSQL_PASSWORD"]),
        database=str(cfg["MYSQL_DB"]),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        recipient = demo_recipient()
        leader_email = demo_leader_email() or None
        purchase_no = str(cfg.get("purchase_no") or cfg.get("PO_NO") or cfg.get("PURCHASE_NO") or DEFAULT_PURCHASE_NO).strip()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE purchase_orders
                SET purchaser_email=%s,
                    buyer_email=%s,
                    leader_email=%s,
                    updated_at=NOW()
                WHERE purchase_no=%s
                """,
                (recipient, recipient, leader_email, purchase_no),
            )
            cur.execute(
                """
                SELECT purchase_no, purchaser_email, leader_email
                FROM purchase_orders
                WHERE purchase_no=%s
                LIMIT 1
                """,
                (purchase_no,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return row or {}


def reset_demo_state() -> None:
    run_cmd([PYTHON, "scripts/reset_demo_state.py"])


def resolve_invoice_path(file_name: str) -> Path:
    path = (ROOT / "invoices" / file_name).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def with_overrides(cfg: Dict[str, Any], **overrides: Any) -> Dict[str, Any]:
    merged = dict(cfg)
    merged.update(overrides)
    return merged


def close_service(svc: Any) -> None:
    db = getattr(getattr(svc, "invoice_repo", None), "db", None)
    if db and hasattr(db, "close"):
        db.close()


def fetch_invoice_state(cfg: Dict[str, Any], invoice_id: int) -> Dict[str, Any]:
    svc = build_service(cfg)
    try:
        db = svc.invoice_repo.db
        invoice = db.fetch_one(
            """
            SELECT id, invoice_code, invoice_number, purchase_order_no, expected_amount,
                   amount_diff, risk_flag, invoice_status, notify_personal_status,
                   notify_leader_status, unique_hash
            FROM invoices
            WHERE id=%s
            """,
            (invoice_id,),
        )
        items = db.fetch_all(
            """
            SELECT item_name, item_spec, item_quantity, item_unit_price, item_amount, tax_rate, tax_amount
            FROM invoice_items
            WHERE invoice_id=%s
            ORDER BY id ASC
            """,
            (invoice_id,),
        )
        events = db.fetch_all(
            """
            SELECT event_type, event_status, payload
            FROM invoice_events
            WHERE invoice_id=%s
            ORDER BY id ASC
            """,
            (invoice_id,),
        )
        for event in events:
            payload = event.get("payload")
            if isinstance(payload, str):
                try:
                    event["payload"] = json.loads(payload)
                except Exception:
                    pass
        counts = db.fetch_one(
            """
            SELECT COUNT(*) AS invoice_count
            FROM invoices
            WHERE unique_hash=%s
            """,
            ((invoice or {}).get("unique_hash"),),
        )
        return {
            "invoice": invoice,
            "items": items,
            "events": events,
            "invoice_count_for_hash": int((counts or {}).get("invoice_count") or 0),
        }
    finally:
        close_service(svc)


def latest_email_event(events: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    matches = [event for event in events if event.get("event_type") == "EMAIL_ALERT"]
    return matches[-1] if matches else None


def process_invoice(file_name: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    svc = build_service(cfg)
    try:
        result = process_one_image(str(resolve_invoice_path(file_name)), cfg, svc)
        summary = {
            "result": {
                "ok": result.ok,
                "action": result.action,
                "invoice_id": result.invoice_id,
                "unique_hash": result.unique_hash,
                "error": result.error,
            }
        }
        if result.invoice_id:
            summary.update(fetch_invoice_state(cfg, int(result.invoice_id)))
        return summary
    finally:
        close_service(svc)


def concurrent_worker(file_name: str, queue) -> None:
    cfg = current_cfg()
    summary = process_invoice(file_name, cfg)
    queue.put(summary)


def run_concurrent_duplicate(file_name: str) -> List[Dict[str, Any]]:
    ctx = get_context("spawn")
    queue = ctx.Queue()
    processes = [ctx.Process(target=concurrent_worker, args=(file_name, queue)) for _ in range(2)]
    for proc in processes:
        proc.start()

    results: List[Dict[str, Any]] = []
    try:
        for _ in processes:
            try:
                results.append(queue.get(timeout=360))
            except Empty as exc:
                raise RuntimeError(f"Timed out waiting for concurrent worker result: {exc}") from exc
    finally:
        for proc in processes:
            proc.join(timeout=30)
            if proc.is_alive():
                proc.terminate()

    return results


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def scenario_cc_and_duplicate(cfg: Dict[str, Any]) -> Dict[str, Any]:
    reset_demo_state()
    recipient_row = align_demo_purchase_order_recipients(cfg)

    first = process_invoice("invoice.jpg", cfg)
    second = process_invoice("invoice.jpg", cfg)

    first_result = first["result"]
    second_result = second["result"]
    first_events = first["events"]
    first_email = latest_email_event(first_events) or {}
    first_payload = first_email.get("payload") if isinstance(first_email.get("payload"), dict) else {}
    sent_email_events = [event for event in first_events if event.get("event_type") == "EMAIL_ALERT" and event.get("event_status") == "SENT"]

    assert_true(first_result["action"] == "inserted", f"Expected first insert, got {first_result}")
    assert_true(second_result["action"] == "skipped", f"Expected duplicate skip, got {second_result}")
    assert_true(first["invoice_count_for_hash"] == 1, f"Duplicate insert created multiple rows: {first['invoice_count_for_hash']}")
    assert_true(first_email.get("event_status") == "SENT", f"Expected EMAIL_ALERT/SENT, got {first_email}")
    assert_true(first_payload.get("to") == demo_recipient(), f"Unexpected alert recipient: {first_payload}")
    assert_true(first_payload.get("cc") == ([demo_leader_email()] if demo_leader_email() else []), f"Unexpected cc routing: {first_payload}")
    assert_true(len(sent_email_events) == 1, f"Duplicate processing sent extra alert emails: {sent_email_events}")

    return {
        "scenario": "cc_and_duplicate",
        "recipient_row": recipient_row,
        "first": first_result,
        "second": second_result,
        "email_payload": first_payload,
        "email_event_count": len(sent_email_events),
    }


def scenario_concurrent_reentry(cfg: Dict[str, Any]) -> Dict[str, Any]:
    reset_demo_state()
    align_demo_purchase_order_recipients(cfg)

    results = run_concurrent_duplicate("invoice.jpg")
    actions = sorted(str((result.get("result") or {}).get("action")) for result in results)
    errors = [result for result in results if not (result.get("result") or {}).get("ok")]
    invoice_ids = [int((result.get("result") or {}).get("invoice_id") or 0) for result in results if (result.get("result") or {}).get("invoice_id")]

    assert_true(not errors, f"Concurrent duplicate processing returned errors: {errors}")
    assert_true(actions == ["inserted", "skipped"], f"Expected one inserted and one skipped, got {actions}")
    assert_true(invoice_ids, f"Concurrent workers returned no invoice ids: {results}")

    state = fetch_invoice_state(cfg, invoice_ids[0])
    email_events = [event for event in state["events"] if event.get("event_type") == "EMAIL_ALERT"]
    sent_events = [event for event in email_events if event.get("event_status") == "SENT"]

    assert_true(state["invoice_count_for_hash"] == 1, f"Concurrent processing inserted duplicate rows: {state['invoice_count_for_hash']}")
    assert_true(len(sent_events) == 1, f"Concurrent processing produced unexpected email events: {email_events}")

    return {
        "scenario": "concurrent_reentry",
        "actions": actions,
        "invoice_count_for_hash": state["invoice_count_for_hash"],
        "email_event_count": len(email_events),
        "sent_email_event_count": len(sent_events),
    }


def scenario_retry_after_email_failure(cfg: Dict[str, Any]) -> Dict[str, Any]:
    reset_demo_state()
    align_demo_purchase_order_recipients(cfg)

    bad_cfg = with_overrides(
        cfg,
        SMTP_HOST="127.0.0.1",
        SMTP_PORT=1,
        SMTP_USE_TLS=False,
        SMTP_USE_SSL=False,
    )

    first = process_invoice("\u53d1\u79684.jpg", bad_cfg)
    second = process_invoice("\u53d1\u79684.jpg", cfg)

    first_result = first["result"]
    second_result = second["result"]
    second_events = second["events"]
    email_statuses = [event.get("event_status") for event in second_events if event.get("event_type") == "EMAIL_ALERT"]
    latest_email = latest_email_event(second_events) or {}
    latest_payload = latest_email.get("payload") if isinstance(latest_email.get("payload"), dict) else {}

    assert_true(first_result["action"] == "inserted", f"Expected first insert under bad SMTP, got {first_result}")
    assert_true(second_result["action"] == "skipped", f"Expected retry to skip duplicate row, got {second_result}")
    assert_true(email_statuses == ["FAILED", "SENT"], f"Expected FAILED then SENT email history, got {email_statuses}")
    assert_true(latest_payload.get("to") == demo_recipient(), f"Retry sent to wrong recipient: {latest_payload}")
    assert_true(latest_payload.get("cc") == ([demo_leader_email()] if demo_leader_email() else []), f"Retry cc mismatch: {latest_payload}")

    return {
        "scenario": "retry_after_email_failure",
        "first": first_result,
        "second": second_result,
        "email_statuses": email_statuses,
        "latest_email_payload": latest_payload,
    }


def scenario_dify_fallback(cfg: Dict[str, Any]) -> Dict[str, Any]:
    reset_demo_state()
    align_demo_purchase_order_recipients(cfg)

    bad_dify_cfg = with_overrides(
        cfg,
        DIFY_BASE_URL="http://127.0.0.1:9/v1",
        dify_base_url="http://127.0.0.1:9/v1",
        DIFY_RETRY_MAX=1,
    )

    result = process_invoice("in2.jpg", bad_dify_cfg)
    result_info = result["result"]
    invoice = result["invoice"]
    email_event = latest_email_event(result["events"]) or {}
    payload = email_event.get("payload") if isinstance(email_event.get("payload"), dict) else {}

    assert_true(result_info["action"] == "inserted", f"Fallback run did not insert invoice: {result_info}")
    assert_true(int((invoice or {}).get("risk_flag") or 0) == 1, f"Fallback run did not mark risk: {invoice}")
    assert_true(len(result["items"]) >= 1, f"Fallback run produced no invoice items: {result}")
    assert_true(email_event.get("event_status") == "SENT", f"Fallback run did not send alert: {email_event}")
    assert_true(payload.get("to") == demo_recipient(), f"Fallback run sent to wrong recipient: {payload}")
    assert_true(payload.get("cc") == ([demo_leader_email()] if demo_leader_email() else []), f"Fallback cc mismatch: {payload}")

    return {
        "scenario": "dify_fallback",
        "result": result_info,
        "item_count": len(result["items"]),
        "amount_diff": (invoice or {}).get("amount_diff"),
        "email_payload": payload,
    }


def main() -> None:
    load_env(override=True)
    cfg = load_flat_config()

    run_cmd(["docker", "compose", "up", "-d", "mysql"])
    run_cmd([PYTHON, "scripts/apply_schema.py"])
    align_demo_purchase_order_recipients(cfg)
    run_cmd([PYTHON, "scripts/check_env.py"])

    ocr_proc = ensure_ocr_process(str(cfg["OCR_BASE_URL"]).rstrip("/"), timeout_sec=120)

    try:
        scenarios = [
            scenario_cc_and_duplicate(cfg),
            scenario_concurrent_reentry(cfg),
            scenario_retry_after_email_failure(cfg),
            scenario_dify_fallback(cfg),
        ]
        summary = {
            "recipient": demo_recipient(),
            "leader_email": demo_leader_email() or None,
            "scenario_count": len(scenarios),
            "scenarios": scenarios,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    finally:
        if ocr_proc:
            try:
                ocr_proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
