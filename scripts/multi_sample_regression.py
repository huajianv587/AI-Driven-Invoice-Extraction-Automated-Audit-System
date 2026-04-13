from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config
from src.main import build_service
from src.services.ingestion_service import process_one_image


PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")


def is_local_host(host: str) -> bool:
    return (host or "").strip().lower() in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}


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


def wait_for_mailpit_count(expected_count: int, timeout_sec: int = 60) -> list[dict]:
    deadline = time.time() + timeout_sec
    last_messages: list[dict] = []
    while time.time() < deadline:
        inbox = requests.get("http://127.0.0.1:8025/api/v1/messages", timeout=10).json()
        messages = inbox.get("messages", [])
        last_messages = messages
        if len(messages) >= expected_count:
            return messages
        time.sleep(2)
    raise RuntimeError(f"Mailpit captured {len(last_messages)} message(s), expected at least {expected_count}.")


def list_sample_invoices() -> list[Path]:
    preferred = ["invoice.jpg", "in2.jpg", "发票3.jpg", "发票4.jpg"]
    paths: list[Path] = []
    for name in preferred:
        p = (ROOT / "invoices" / name).resolve()
        if p.exists():
            paths.append(p)

    if len(paths) >= 4:
        return paths

    discovered = sorted(
        p.resolve()
        for p in (ROOT / "invoices").iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
    )
    return discovered


def resolve_requested_samples(argv: list[str]) -> list[Path]:
    requested = [arg.strip() for arg in argv if arg.strip()]
    if not requested:
        return list_sample_invoices()

    resolved: list[Path] = []
    for raw in requested:
        candidate = Path(raw)
        if not candidate.is_absolute():
            invoice_candidate = ROOT / "invoices" / raw
            candidate = invoice_candidate if invoice_candidate.exists() else ROOT / raw
        candidate = candidate.resolve()
        if not candidate.exists():
            raise FileNotFoundError(candidate)
        resolved.append(candidate)
    return resolved


def align_demo_purchase_order_recipients(cfg: dict[str, Any]) -> None:
    purchase_no = str(cfg.get("purchase_no") or cfg.get("PO_NO") or cfg.get("PURCHASE_NO") or "PO-DEMO-001").strip()
    recipient = str(cfg.get("ALERT_FALLBACK_TO") or cfg.get("SMTP_FROM_EMAIL") or cfg.get("SMTP_USER") or "").strip()
    leader_email = os.getenv("DEMO_LEADER_EMAIL", "").strip()
    if not purchase_no or not recipient:
        return

    import pymysql

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
                (recipient, recipient, leader_email or None, purchase_no),
            )
    finally:
        conn.close()


def main() -> None:
    run_cmd([PYTHON, "scripts/check_env.py"])

    load_env(override=True)
    cfg = load_flat_config()
    ocr_base_url = str(cfg["OCR_BASE_URL"]).rstrip("/")
    smtp_host = str(cfg.get("SMTP_HOST") or "")
    use_mailpit = is_local_host(smtp_host)

    docker_services = ["mysql", "mailpit"] if use_mailpit else ["mysql"]
    run_cmd(["docker", "compose", "up", "-d", *docker_services])
    run_cmd([PYTHON, "scripts/apply_schema.py"])
    run_cmd([PYTHON, "scripts/reset_demo_state.py"])
    if not use_mailpit:
        align_demo_purchase_order_recipients(cfg)

    started = []
    ocr_proc = ensure_ocr_process(ocr_base_url, [PYTHON, "ocr_server.py"], timeout_sec=120)
    if ocr_proc:
        started.append(ocr_proc)

    samples = resolve_requested_samples(sys.argv[1:])
    if not samples:
        raise RuntimeError("No invoice samples were selected.")

    svc = build_service(cfg)
    try:
        db = svc.invoice_repo.db
        sample_results = []
        for sample in samples:
            result = process_one_image(str(sample), cfg, svc)
            if not result.ok or result.action != "inserted":
                raise RuntimeError(f"Unexpected ingest result for {sample.name}: {result}")

            invoice = db.fetch_one(
                """
                SELECT id, invoice_code, invoice_number, purchase_order_no, total_amount_with_tax,
                       expected_amount, amount_diff, risk_flag, invoice_status, unique_hash
                FROM invoices
                WHERE id=%s
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
            email_event = db.fetch_one(
                """
                SELECT event_type, event_status, payload
                FROM invoice_events
                WHERE invoice_id=%s AND event_type='EMAIL_ALERT'
                ORDER BY id DESC
                LIMIT 1
                """,
                (result.invoice_id,),
            )
            if email_event and isinstance(email_event.get("payload"), str):
                try:
                    email_event["payload"] = json.loads(email_event["payload"])
                except Exception:
                    pass

            if int(invoice.get("risk_flag") or 0) != 1:
                raise RuntimeError(f"{sample.name} was expected to be risky but risk_flag={invoice.get('risk_flag')}.")
            if not items:
                raise RuntimeError(f"{sample.name} produced no invoice_items.")
            if not email_event or email_event.get("event_status") != "SENT":
                raise RuntimeError(f"{sample.name} did not produce EMAIL_ALERT/SENT. event={email_event}")

            payload: dict[str, Any] = email_event.get("payload") if isinstance(email_event.get("payload"), dict) else {}

            sample_results.append(
                {
                    "file": sample.name,
                    "invoice_id": result.invoice_id,
                    "invoice_code": invoice.get("invoice_code"),
                    "invoice_number": invoice.get("invoice_number"),
                    "total_amount_with_tax": invoice.get("total_amount_with_tax"),
                    "expected_amount": invoice.get("expected_amount"),
                    "amount_diff": invoice.get("amount_diff"),
                    "risk_flag": invoice.get("risk_flag"),
                    "item_count": len(items),
                    "email_to": payload.get("to"),
                    "email_cc": payload.get("cc"),
                    "email_event": email_event,
                }
            )

        summary = {
            "smtp_mode": "mailpit" if use_mailpit else "external",
            "sample_count": len(sample_results),
            "samples": sample_results,
        }
        if use_mailpit:
            messages = wait_for_mailpit_count(len(sample_results), timeout_sec=60)
            summary["mailpit_message_count"] = len(messages)
        else:
            summary["mailpit_message_count"] = None
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
