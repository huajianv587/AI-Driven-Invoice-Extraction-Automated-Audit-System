from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config
from src.api.security import hash_password
from src.db.mysql_client import MySQLClient


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def demo_password_for(role: str) -> str:
    defaults = {
        "admin": "ChangeMe123!",
        "reviewer": "Reviewer123!",
        "ops": "OpsUser123!",
        "inactive": "Inactive123!",
    }
    return defaults[role]


def demo_users(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    admin_email = str(cfg.get("AUTH_BOOTSTRAP_ADMIN_EMAIL") or "admin@invoice-audit.local").strip().lower()
    admin_name = str(cfg.get("AUTH_BOOTSTRAP_ADMIN_NAME") or "Platform Admin").strip() or "Platform Admin"
    admin_password = str(cfg.get("AUTH_BOOTSTRAP_ADMIN_PASSWORD") or demo_password_for("admin")).strip()
    return [
        {
            "email": admin_email,
            "full_name": admin_name,
            "password": admin_password,
            "role": "admin",
            "is_active": 1,
        },
        {
            "email": "reviewer@invoice-audit.local",
            "full_name": "Riley Reviewer",
            "password": demo_password_for("reviewer"),
            "role": "reviewer",
            "is_active": 1,
        },
        {
            "email": "ops@invoice-audit.local",
            "full_name": "Owen Operator",
            "password": demo_password_for("ops"),
            "role": "ops",
            "is_active": 1,
        },
        {
            "email": "inactive@invoice-audit.local",
            "full_name": "Inactive Auditor",
            "password": demo_password_for("inactive"),
            "role": "reviewer",
            "is_active": 0,
        },
    ]


def upsert_demo_users(db: MySQLClient, cfg: Dict[str, Any]) -> None:
    users = demo_users(cfg)
    emails = [user["email"] for user in users]
    if emails:
        placeholders = ", ".join(["%s"] * len(emails))
        db.execute(
            f"""
            DELETE t
            FROM app_refresh_tokens t
            INNER JOIN app_users u ON u.id = t.user_id
            WHERE u.email IN ({placeholders})
            """,
            tuple(emails),
        )

    sql = """
    INSERT INTO app_users(email, full_name, password_hash, role, is_active)
    VALUES(%s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
      full_name=VALUES(full_name),
      password_hash=VALUES(password_hash),
      role=VALUES(role),
      is_active=VALUES(is_active),
      updated_at=NOW()
    """
    db.executemany(
        sql,
        [
            (
                user["email"],
                user["full_name"],
                hash_password(str(user["password"])),
                user["role"],
                int(user["is_active"]),
            )
            for user in users
        ],
    )


def upsert_purchase_orders(db: MySQLClient) -> None:
    rows = [
        ("PO-DEMO-001", "Atlas Components Ltd", "Morgan Lee", 100000.00, "Approved"),
        ("PO-DEMO-002", "Helio Logistics", "Nora Patel", 64000.00, "Approved"),
        ("PO-DEMO-003", "Quartz Robotics", "Elliot Park", 38000.00, "Approved"),
        ("PO-DEMO-004", "Bluefield Packaging", "Mia Chen", 72000.00, "Approved"),
        ("PO-DEMO-005", "Cedar Cloud Services", "Sofia Reyes", 18800.00, "Pending"),
        ("PO-DEMO-006", "Northstar Calibration", "Victor Huang", 41200.00, "Approved"),
    ]
    sql = """
    INSERT INTO purchase_orders(
      purchase_no, po_number, supplier, supplier_name, purchaser_name,
      purchaser_email, buyer_email, leader_email, total_amount_with_tax,
      expected_amount, purchase_order_date, status, notes
    )
    VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
      po_number=VALUES(po_number),
      supplier=VALUES(supplier),
      supplier_name=VALUES(supplier_name),
      purchaser_name=VALUES(purchaser_name),
      purchaser_email=VALUES(purchaser_email),
      buyer_email=VALUES(buyer_email),
      leader_email=VALUES(leader_email),
      total_amount_with_tax=VALUES(total_amount_with_tax),
      expected_amount=VALUES(expected_amount),
      purchase_order_date=VALUES(purchase_order_date),
      status=VALUES(status),
      notes=VALUES(notes),
      updated_at=NOW()
    """
    params = [
        (
            purchase_no,
            purchase_no,
            supplier,
            supplier,
            owner,
            f"{owner.lower().replace(' ', '.')}@local.test",
            f"{owner.lower().replace(' ', '.')}@local.test",
            "finance-leader@local.test",
            amount,
            amount,
            "2026-04-01",
            status,
            "Deterministic Web UI demo purchase order.",
        )
        for purchase_no, supplier, owner, amount, status in rows
    ]
    db.executemany(sql, params)


def insert_invoice(db: MySQLClient, row: Dict[str, Any]) -> int:
    now = dt.datetime.now().replace(microsecond=0)
    created_at = now - dt.timedelta(days=int(row.pop("age_days")))
    invoice_id = db.execute_returning_id(
        """
        INSERT INTO invoices(
          invoice_type, invoice_code, invoice_number, invoice_date,
          invoice_status, seller_name, seller_tax_id, buyer_name, buyer_tax_id,
          total_amount_without_tax, total_tax_amount, total_amount_with_tax,
          purchase_order_no, source_file_path, raw_ocr_json, llm_json,
          expected_amount, amount_diff, risk_flag, risk_reason,
          handler_user, handler_reason, handled_at,
          notify_personal_status, notify_leader_status, unique_hash,
          created_at, updated_at
        )
        VALUES(
          %s, %s, %s, %s,
          %s, %s, %s, %s, %s,
          %s, %s, %s,
          %s, %s, %s, %s,
          %s, %s, %s, %s,
          %s, %s, %s,
          %s, %s, %s,
          %s, %s
        )
        """,
        (
            "VAT special invoice",
            row["invoice_code"],
            row["invoice_number"],
            row["invoice_date"],
            row["invoice_status"],
            row["seller_name"],
            row["seller_tax_id"],
            row["buyer_name"],
            row["buyer_tax_id"],
            row["amount_without_tax"],
            row["tax_amount"],
            row["total_amount"],
            row["purchase_order_no"],
            f"demo/{row['invoice_number']}.jpg",
            as_json({
                "source": "web-demo-seed",
                "invoice_number": row["invoice_number"],
                "test_run_id": os.getenv("WEB_DEEP_TEST_RUN_ID", "").strip() or None,
                "external_prefix": os.getenv("WEB_DEEP_EXTERNAL_PREFIX", "").strip() or None,
            }),
            as_json({"purchase_order_no": row["purchase_order_no"], "confidence": 0.98}),
            row["expected_amount"],
            row["amount_diff"],
            1 if row["risk_flag"] else 0,
            as_json(row["risk_reason"]),
            row.get("handler_user"),
            row.get("handler_reason"),
            row.get("handled_at"),
            row.get("notify_personal_status", "NotSent"),
            row.get("notify_leader_status", "NotSent"),
            stable_hash(f"web-demo:{row['invoice_code']}:{row['invoice_number']}"),
            created_at,
            created_at,
        ),
    )
    return invoice_id


def insert_items(db: MySQLClient, invoice_id: int, items: Iterable[Dict[str, Any]]) -> None:
    db.executemany(
        """
        INSERT INTO invoice_items(
          invoice_id, item_name, item_spec, item_unit, item_quantity,
          item_unit_price, item_amount, tax_rate, tax_amount
        )
        VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                invoice_id,
                item["name"],
                item.get("spec"),
                item.get("unit", "ea"),
                item.get("quantity", 1),
                item.get("unit_price"),
                item.get("amount"),
                item.get("tax_rate", 0.13),
                item.get("tax_amount"),
            )
            for item in items
        ],
    )


def insert_events(db: MySQLClient, invoice_id: int, events: Iterable[Dict[str, Any]]) -> None:
    db.executemany(
        """
        INSERT INTO invoice_events(invoice_id, event_type, event_status, payload, created_at)
        VALUES(%s, %s, %s, %s, %s)
        """,
        [
            (
                invoice_id,
                event["type"],
                event["status"],
                as_json(event.get("payload", {})),
                event.get("created_at", "2026-04-15 09:00:00"),
            )
            for event in events
        ],
    )


def insert_review_task(db: MySQLClient, invoice_id: int, invoice: Dict[str, Any]) -> None:
    if not invoice.get("review_result"):
        return
    db.execute(
        """
        INSERT INTO invoice_review_tasks(
          invoice_id, purchase_order_no, unique_hash, review_result,
          handler_user, handling_note, source_channel, created_at
        )
        VALUES(%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            invoice_id,
            invoice["purchase_order_no"],
            stable_hash(f"web-demo:{invoice['invoice_code']}:{invoice['invoice_number']}"),
            invoice["review_result"],
            invoice.get("handler_user"),
            invoice.get("handler_reason"),
            "web_app",
            invoice.get("review_created_at", "2026-04-15 10:00:00"),
        ),
    )


def insert_state_transition(db: MySQLClient, invoice_id: int, invoice: Dict[str, Any]) -> None:
    if not invoice.get("review_result"):
        return
    db.execute(
        """
        INSERT INTO invoice_state_transitions(
          invoice_id, from_status, to_status, actor_email, actor_role, reason, idempotency_key, created_at
        )
        VALUES(%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            invoice_id,
            "Pending",
            invoice["review_result"],
            "seed@invoice-audit.local",
            "admin",
            invoice.get("handler_reason"),
            stable_hash(f"seed-transition:{invoice['invoice_code']}:{invoice['invoice_number']}")[:128],
            invoice.get("review_created_at", "2026-04-15 10:00:00"),
        ),
    )


def insert_sync(db: MySQLClient, invoice_id: int, sync: Dict[str, Any] | None) -> None:
    if not sync:
        return
    db.execute(
        """
        INSERT INTO invoice_feishu_sync(
          invoice_id, feishu_record_id, synced_at, sync_error, created_at, updated_at
        )
        VALUES(%s, %s, %s, %s, %s, %s)
        """,
        (
            invoice_id,
            sync.get("record_id"),
            sync.get("synced_at"),
            sync.get("error"),
            sync.get("created_at", "2026-04-15 10:30:00"),
            sync.get("updated_at", "2026-04-15 10:30:00"),
        ),
    )


def demo_invoices() -> List[Dict[str, Any]]:
    return [
        {
            "age_days": 0,
            "invoice_code": "WEB-DEMO-A1",
            "invoice_number": "INV-900001",
            "invoice_date": "2026-04-15",
            "invoice_status": "Pending",
            "seller_name": "Atlas Components Ltd",
            "seller_tax_id": "US-ATLAS-001",
            "buyer_name": "Northwind Retail Group",
            "buyer_tax_id": "US-NW-100",
            "amount_without_tax": 110619.47,
            "tax_amount": 14380.53,
            "total_amount": 125000.00,
            "expected_amount": 100000.00,
            "amount_diff": 25000.00,
            "purchase_order_no": "PO-DEMO-001",
            "risk_flag": True,
            "risk_reason": [{"type": "amount_mismatch", "message": "Invoice exceeds approved purchase order by 25%."}],
            "notify_personal_status": "Sent",
            "notify_leader_status": "Pending",
            "items": [
                {"name": "Precision motor assembly", "quantity": 18, "unit_price": 4920.35, "amount": 88566.30, "tax_amount": 11513.62},
                {"name": "Field calibration kit", "quantity": 4, "unit_price": 5513.29, "amount": 22053.17, "tax_amount": 2866.91},
            ],
            "events": [
                {"type": "OCR_PARSED", "status": "OK", "payload": {"confidence": 0.97}},
                {"type": "RISK_EVALUATED", "status": "FLAGGED", "payload": {"rule": "amount_mismatch"}},
                {"type": "EMAIL_ALERT", "status": "SENT", "payload": {"channel": "mailpit"}},
            ],
            "sync": None,
        },
        {
            "age_days": 1,
            "invoice_code": "WEB-DEMO-B2",
            "invoice_number": "INV-900002",
            "invoice_date": "2026-04-14",
            "invoice_status": "Approved",
            "seller_name": "Helio Logistics",
            "seller_tax_id": "US-HELIO-002",
            "buyer_name": "Northwind Retail Group",
            "buyer_tax_id": "US-NW-100",
            "amount_without_tax": 56637.17,
            "tax_amount": 7362.83,
            "total_amount": 64000.00,
            "expected_amount": 64000.00,
            "amount_diff": 0.00,
            "purchase_order_no": "PO-DEMO-002",
            "risk_flag": False,
            "risk_reason": [],
            "handler_user": "Mia Chen",
            "handler_reason": "Matched PO, amount, and supplier record.",
            "handled_at": "2026-04-14 16:20:00",
            "review_result": "Approved",
            "review_created_at": "2026-04-14 16:20:00",
            "items": [
                {"name": "Regional freight lane", "quantity": 1, "unit_price": 56637.17, "amount": 56637.17, "tax_amount": 7362.83},
            ],
            "events": [
                {"type": "OCR_PARSED", "status": "OK", "payload": {"confidence": 0.99}},
                {"type": "WORK_ORDER_SUBMITTED", "status": "Approved", "payload": {"handler_user": "Mia Chen"}},
                {"type": "FEISHU_SYNC", "status": "OK", "payload": {"record_id": "rec_demo_synced_002"}},
            ],
            "sync": {"record_id": "rec_demo_synced_002", "synced_at": "2026-04-14 16:30:00"},
        },
        {
            "age_days": 2,
            "invoice_code": "WEB-DEMO-C3",
            "invoice_number": "INV-900003",
            "invoice_date": "2026-04-13",
            "invoice_status": "NeedsReview",
            "seller_name": "Quartz Robotics",
            "seller_tax_id": "US-QUARTZ-003",
            "buyer_name": "Northwind Retail Group",
            "buyer_tax_id": "US-NW-100",
            "amount_without_tax": 37079.65,
            "tax_amount": 4820.35,
            "total_amount": 41900.00,
            "expected_amount": 38000.00,
            "amount_diff": 3900.00,
            "purchase_order_no": "PO-DEMO-003",
            "risk_flag": True,
            "risk_reason": [{"type": "sync_exception", "message": "Requires replay after Feishu connector recovery."}],
            "handler_user": "Ops Review",
            "handler_reason": "Held for connector recovery.",
            "handled_at": "2026-04-13 11:45:00",
            "review_result": "NeedsReview",
            "review_created_at": "2026-04-13 11:45:00",
            "items": [
                {"name": "Robotic inspection module", "quantity": 2, "unit_price": 18539.83, "amount": 37079.65, "tax_amount": 4820.35},
            ],
            "events": [
                {"type": "OCR_PARSED", "status": "OK", "payload": {"confidence": 0.94}},
                {"type": "FEISHU_SYNC", "status": "FAILED", "payload": {"reason": "rate_limited"}},
            ],
            "sync": {
                "error": "Demo connector rate limit from Feishu replay queue.",
                "created_at": "2026-04-13 11:50:00",
                "updated_at": "2026-04-13 11:50:00",
            },
        },
        {
            "age_days": 3,
            "invoice_code": "WEB-DEMO-D4",
            "invoice_number": "INV-900004",
            "invoice_date": "2026-04-12",
            "invoice_status": "Rejected",
            "seller_name": "Bluefield Packaging",
            "seller_tax_id": "US-BLUE-004",
            "buyer_name": "Northwind Retail Group",
            "buyer_tax_id": "US-NW-100",
            "amount_without_tax": 69026.55,
            "tax_amount": 8973.45,
            "total_amount": 78000.00,
            "expected_amount": 72000.00,
            "amount_diff": 6000.00,
            "purchase_order_no": "PO-DEMO-004",
            "risk_flag": True,
            "risk_reason": [{"type": "seller_name_mismatch", "message": "Supplier alias differs from approved PO vendor."}],
            "handler_user": "Finance Lead",
            "handler_reason": "Rejected until vendor alias is reconciled.",
            "handled_at": "2026-04-12 15:05:00",
            "review_result": "Rejected",
            "review_created_at": "2026-04-12 15:05:00",
            "items": [
                {"name": "Retail packaging batch", "quantity": 1, "unit_price": 69026.55, "amount": 69026.55, "tax_amount": 8973.45},
            ],
            "events": [{"type": "WORK_ORDER_SUBMITTED", "status": "Rejected", "payload": {"handler_user": "Finance Lead"}}],
            "sync": {"record_id": "rec_demo_synced_004", "synced_at": "2026-04-12 15:20:00"},
        },
        {
            "age_days": 5,
            "invoice_code": "WEB-DEMO-E5",
            "invoice_number": "INV-900005",
            "invoice_date": "2026-04-10",
            "invoice_status": "Pending",
            "seller_name": "Cedar Cloud Services",
            "seller_tax_id": "US-CEDAR-005",
            "buyer_name": "Northwind Retail Group",
            "buyer_tax_id": "US-NW-100",
            "amount_without_tax": 16637.17,
            "tax_amount": 2162.83,
            "total_amount": 18800.00,
            "expected_amount": 18800.00,
            "amount_diff": 0.00,
            "purchase_order_no": "PO-DEMO-005",
            "risk_flag": False,
            "risk_reason": [],
            "items": [{"name": "Cloud usage allocation", "quantity": 1, "unit_price": 16637.17, "amount": 16637.17, "tax_amount": 2162.83}],
            "events": [{"type": "OCR_PARSED", "status": "OK", "payload": {"confidence": 0.96}}],
            "sync": None,
        },
        {
            "age_days": 6,
            "invoice_code": "WEB-DEMO-F6",
            "invoice_number": "INV-900006",
            "invoice_date": "2026-04-09",
            "invoice_status": "Pending",
            "seller_name": "Northstar Calibration",
            "seller_tax_id": "US-NORTH-006",
            "buyer_name": "Northwind Retail Group",
            "buyer_tax_id": "US-NW-100",
            "amount_without_tax": 40353.98,
            "tax_amount": 5246.02,
            "total_amount": 45600.00,
            "expected_amount": 41200.00,
            "amount_diff": 4400.00,
            "purchase_order_no": "PO-DEMO-006",
            "risk_flag": True,
            "risk_reason": [{"type": "amount_mismatch", "message": "Calibration overage needs reviewer confirmation."}],
            "items": [{"name": "Annual calibration program", "quantity": 1, "unit_price": 40353.98, "amount": 40353.98, "tax_amount": 5246.02}],
            "events": [{"type": "RISK_EVALUATED", "status": "FLAGGED", "payload": {"rule": "amount_mismatch"}}],
            "sync": None,
        },
    ]


def main() -> None:
    load_env(override=True)
    cfg = load_flat_config()
    db = MySQLClient(
        host=cfg["mysql_host"],
        port=int(cfg["mysql_port"]),
        user=cfg["mysql_user"],
        password=cfg["mysql_password"],
        db=cfg["mysql_db"],
    )
    try:
        upsert_demo_users(db, cfg)
        upsert_purchase_orders(db)
        created_ids: List[int] = []
        for invoice in demo_invoices():
            invoice_copy = dict(invoice)
            items = invoice_copy.pop("items")
            events = invoice_copy.pop("events")
            sync = invoice_copy.pop("sync", None)
            invoice_id = insert_invoice(db, invoice_copy)
            insert_items(db, invoice_id, items)
            insert_events(db, invoice_id, events)
            insert_review_task(db, invoice_id, invoice_copy)
            insert_state_transition(db, invoice_id, invoice_copy)
            insert_sync(db, invoice_id, sync)
            created_ids.append(invoice_id)
        print(json.dumps({"ok": True, "invoice_ids": created_ids}, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
