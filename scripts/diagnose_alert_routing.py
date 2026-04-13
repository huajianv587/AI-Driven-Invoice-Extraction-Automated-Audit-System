from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pymysql
import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_config


def is_local_host(host: str) -> bool:
    return (host or "").strip().lower() in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}


def is_demo_email(email: str) -> bool:
    text = (email or "").strip().lower()
    if not text or "@" not in text:
        return False
    domain = text.rsplit("@", 1)[-1]
    return domain in {"local.test", "example.com", "example.org", "example.net"} or domain.endswith(".local.test")


def fetch_purchase_order(conn: pymysql.connections.Connection, purchase_no: str) -> Dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, purchase_no, purchaser_name, purchaser_email, leader_email,
                   expected_amount, supplier, status
            FROM purchase_orders
            WHERE purchase_no=%s
            LIMIT 1
            """,
            (purchase_no,),
        )
        return cur.fetchone()


def fetch_latest_invoice(conn: pymysql.connections.Connection, purchase_no: str) -> Dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, purchase_order_no, invoice_code, invoice_number, unique_hash,
                   risk_flag, expected_amount, amount_diff, notify_personal_status,
                   notify_leader_status, invoice_status, created_at
            FROM invoices
            WHERE purchase_order_no=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            (purchase_no,),
        )
        return cur.fetchone()


def fetch_latest_email_event(conn: pymysql.connections.Connection, invoice_id: int) -> Dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_status, payload, created_at
            FROM invoice_events
            WHERE invoice_id=%s AND event_type='EMAIL_ALERT'
            ORDER BY id DESC
            LIMIT 1
            """,
            (invoice_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    payload = row.get("payload")
    if isinstance(payload, str):
        try:
            row["payload"] = json.loads(payload)
        except Exception:
            pass
    return row


def fetch_mailpit_messages(limit: int = 10) -> List[Dict[str, Any]]:
    try:
        data = requests.get("http://127.0.0.1:8025/api/v1/messages", timeout=5).json()
    except Exception:
        return []

    messages = data.get("messages") or []
    out: List[Dict[str, Any]] = []
    for msg in messages[:limit]:
        out.append(
            {
                "subject": msg.get("Subject"),
                "to": [item.get("Address") for item in (msg.get("To") or []) if item.get("Address")],
                "from": (msg.get("From") or {}).get("Address"),
                "created": msg.get("Created"),
            }
        )
    return out


def main() -> int:
    cfg = load_config()
    purchase_no = (sys.argv[1] if len(sys.argv) > 1 else cfg.purchase_no or "PO-DEMO-001").strip()

    conn = pymysql.connect(
        host=cfg.mysql.host,
        port=cfg.mysql.port,
        user=cfg.mysql.user,
        password=cfg.mysql.password,
        database=cfg.mysql.db,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        po = fetch_purchase_order(conn, purchase_no)
        latest_invoice = fetch_latest_invoice(conn, purchase_no)
        latest_email_event = fetch_latest_email_event(conn, int(latest_invoice["id"])) if latest_invoice else None
    finally:
        conn.close()

    purchaser_email = ((po or {}).get("purchaser_email") or "").strip()
    leader_email = ((po or {}).get("leader_email") or "").strip()
    to_email = purchaser_email or cfg.email.alert_fallback_to or leader_email
    cc_list = [leader_email] if leader_email and leader_email != to_email else []

    diagnosis: List[str] = []
    if is_local_host(cfg.email.smtp_host):
        diagnosis.append("SMTP_HOST points to local Mailpit, so alerts stay on this machine and do not reach external inboxes.")
    if is_demo_email(to_email) or any(is_demo_email(email) for email in cc_list):
        diagnosis.append("Effective alert recipients are demo addresses from purchase_orders, not real mailboxes.")
    if latest_email_event and latest_email_event.get("event_status") == "SENT":
        diagnosis.append("The alert pipeline already marked the last risky invoice as SENT.")
    elif latest_invoice and int(latest_invoice.get("risk_flag") or 0) == 1:
        diagnosis.append("The latest invoice is risky, but no successful EMAIL_ALERT event was found.")
    elif latest_invoice:
        diagnosis.append("The latest invoice under this purchase order is not marked risky, so no alert should be sent.")
    else:
        diagnosis.append("No invoice was found for this purchase order yet.")

    result = {
        "purchase_order": po,
        "smtp": {
            "host": cfg.email.smtp_host,
            "port": cfg.email.smtp_port,
            "use_tls": cfg.email.use_tls,
            "use_ssl": cfg.email.use_ssl,
            "from_email": cfg.email.from_email,
            "is_local_host": is_local_host(cfg.email.smtp_host),
        },
        "effective_route": {
            "to": to_email,
            "cc": cc_list,
            "fallback_to": cfg.email.alert_fallback_to,
        },
        "latest_invoice": latest_invoice,
        "latest_email_event": latest_email_event,
        "mailpit_messages": fetch_mailpit_messages() if is_local_host(cfg.email.smtp_host) else [],
        "diagnosis": diagnosis,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
