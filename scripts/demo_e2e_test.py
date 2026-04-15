from __future__ import annotations

"""Legacy Streamlit demo regression.

The canonical Web UI regression now lives in frontend/tests and runs with
Playwright against Next.js + FastAPI. Keep this script only for comparing the
old Streamlit work-order loop during migration.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config
from src.main import build_service
from src.services.ingestion_service import process_one_image
from src.ui.streamlit_app import update_invoice_review


PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")


def run_cmd(args: list[str]) -> None:
    subprocess.run(args, cwd=str(ROOT), check=True)


def wait_http(url: str, timeout_sec: int = 120) -> None:
    deadline = time.time() + timeout_sec
    last_error = None
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=5)
            if 200 <= resp.status_code < 400:
                return
        except Exception as exc:
            last_error = exc
        time.sleep(2)
    raise RuntimeError(f"Endpoint not ready: {url} -> {last_error}")


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


def ensure_process(url: str, command: list[str], timeout_sec: int = 120):
    try:
        wait_http(url, timeout_sec=5)
        return None
    except Exception:
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        proc = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_http(url, timeout_sec=timeout_sec)
        return proc


def ensure_ocr_process(base_url: str, command: list[str], timeout_sec: int = 120):
    try:
        wait_ocr(base_url, timeout_sec=5)
        return None
    except Exception:
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        proc = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_ocr(base_url, timeout_sec=timeout_sec)
        return proc


def fetch_mailpit_message() -> dict:
    inbox = requests.get("http://127.0.0.1:8025/api/v1/messages", timeout=10).json()
    messages = inbox.get("messages", [])
    if not messages:
        raise RuntimeError("No Mailpit message captured")
    message_id = messages[0]["ID"]
    resp = requests.get(f"http://127.0.0.1:8025/api/v1/message/{message_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    run_cmd([PYTHON, "scripts/check_env.py"])
    load_env(override=True)
    cfg = load_flat_config()
    ui_port = int(cfg["UI_PORT"])
    ocr_base_url = str(cfg["OCR_BASE_URL"]).rstrip("/")

    run_cmd(["docker", "compose", "up", "-d", "mysql", "mailpit"])
    run_cmd([PYTHON, "scripts/apply_schema.py"])
    run_cmd([PYTHON, "scripts/reset_demo_state.py"])

    started = []
    ocr_proc = ensure_ocr_process(ocr_base_url, [PYTHON, "ocr_server.py"], timeout_sec=120)
    if ocr_proc:
        started.append(ocr_proc)
    ui_proc = ensure_process(
        f"http://127.0.0.1:{ui_port}/?view=dashboard",
        [PYTHON, "-m", "streamlit", "run", "src/ui/streamlit_app.py", "--server.headless", "true", "--server.port", str(ui_port)],
        timeout_sec=120,
    )
    if ui_proc:
        started.append(ui_proc)
    svc = build_service(cfg)
    try:
        invoice_path = str((ROOT / "invoices" / "invoice.jpg").resolve())
        result = process_one_image(invoice_path, cfg, svc)
        if not result.ok or result.action != "inserted":
            raise RuntimeError(f"Unexpected ingest result: {result}")

        message = fetch_mailpit_message()
        form_link = ""
        for line in (message.get("Text") or "").splitlines():
            if line.startswith("Work order form:"):
                form_link = line.split(":", 1)[1].strip()
                break
        if not form_link:
            raise RuntimeError("Work order link not found in email body")

        query = parse_qs(urlparse(form_link).query)
        db = svc.invoice_repo.db
        update_invoice_review(
            db=db,
            invoice_id=int(query["invoice_id"][0]),
            purchase_order_no=query.get("purchase_order_no", [""])[0],
            unique_hash=query.get("unique_hash", [""])[0],
            handler_user="demo.reviewer",
            handler_reason="End-to-end demo review submitted successfully.",
            invoice_status="NeedsReview",
        )

        invoice = db.fetch_one(
            """
            SELECT id, purchase_order_no, expected_amount, amount_diff, risk_flag,
                   invoice_status, handler_user, notify_personal_status, notify_leader_status
            FROM invoices
            WHERE id=%s
            """,
            (result.invoice_id,),
        )
        review_task = db.fetch_one(
            """
            SELECT invoice_id, purchase_order_no, review_result, handler_user, source_channel
            FROM invoice_review_tasks
            WHERE invoice_id=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            (result.invoice_id,),
        )
        items = db.fetch_all(
            """
            SELECT item_name, item_spec, item_quantity, item_unit_price, item_amount, tax_rate, tax_amount
            FROM invoice_items
            WHERE invoice_id=%s
            ORDER BY id ASC
            """,
            (result.invoice_id,),
        )
        events = db.fetch_all(
            """
            SELECT event_type, event_status
            FROM invoice_events
            WHERE invoice_id=%s
            ORDER BY id ASC
            """,
            (result.invoice_id,),
        )

        required_events = {("INGEST", "OK"), ("EMAIL_ALERT", "SENT"), ("WORK_ORDER_SUBMITTED", "NeedsReview")}
        actual_events = {(row["event_type"], row["event_status"]) for row in events}
        missing = sorted(required_events - actual_events)
        if missing:
            raise RuntimeError(f"Missing expected events: {missing}")
        if not items:
            raise RuntimeError("No invoice_items were parsed; OCR fallback / Dify extraction is incomplete.")

        summary = {
            "invoice_result": {
                "invoice_id": result.invoice_id,
                "action": result.action,
                "unique_hash": result.unique_hash,
            },
            "mailpit_subject": message.get("Subject"),
            "work_order_link": form_link,
            "invoice": invoice,
            "review_task": review_task,
            "item_count": len(items),
            "items": items,
            "events": events,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    finally:
        db = getattr(getattr(svc, "invoice_repo", None), "db", None)
        if db and hasattr(db, "close"):
            db.close()
        for proc in started:
            try:
                proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
