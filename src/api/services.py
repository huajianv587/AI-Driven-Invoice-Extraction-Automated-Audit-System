from __future__ import annotations

import datetime as dt
import json
import threading
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from src.api.security import create_access_token, generate_refresh_token, hash_password, hash_refresh_token, verify_password
from src.api.state_machine import InvalidStateTransition, validate_review_transition
from src.db.mysql_client import MySQLClient
from src.jobs.feishu_sync_job import sync_invoices_to_feishu
from src.services.integration_checks import check_dify, check_feishu, check_http_endpoint, check_smtp


CONNECTOR_NAMES = ["OCR", "Dify", "Feishu", "SMTP"]
_CONNECTOR_CACHE_LOCK = threading.Lock()
_CONNECTOR_CACHE: Dict[str, Any] = {"expires_at": 0.0, "rows": [], "cached_at": None}
_FEISHU_RETRY_LOCK = threading.Lock()


class RetryAlreadyRunning(RuntimeError):
    pass


def decode_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", "ignore")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def safe_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def safe_int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(value)
    except Exception:
        return 0


def serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}
    return value


def fmt_day_label(value: Any) -> str:
    if value in (None, ""):
        return "-"
    text = str(value)
    return text[5:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else text


def short_text(value: Any, limit: int = 160) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def utc_now() -> dt.datetime:
    return dt.datetime.utcnow().replace(microsecond=0)


def iso_utc(value: Optional[dt.datetime] = None) -> str:
    return (value or utc_now()).isoformat() + "Z"


def parse_old_secrets(value: Any) -> List[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def device_label_from_user_agent(user_agent: str) -> str:
    text = str(user_agent or "").strip()
    if not text:
        return "Unknown device"
    lowered = text.lower()
    if "mobile" in lowered or "android" in lowered or "iphone" in lowered:
        return "Mobile browser"
    if "playwright" in lowered or "headlesschrome" in lowered:
        return "Automated test browser"
    if "chrome" in lowered:
        return "Chrome browser"
    if "firefox" in lowered:
        return "Firefox browser"
    if "safari" in lowered:
        return "Safari browser"
    return text[:128]


def compact_label(value: Any) -> str:
    text = str(value or "").replace("_", " ").strip()
    if not text:
        return "-"
    chars: List[str] = []
    for idx, char in enumerate(text):
        if idx and char.isupper() and text[idx - 1].islower():
            chars.append(" ")
        chars.append(char)
    compact = "".join(chars).strip()
    return compact[:1].upper() + compact[1:]


def risk_reason_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    normalized = "".join(char for char in text.lower() if char.isalnum())
    mapping = {
        "amountmismatchwithexpected": "Amount gap",
        "amountmismatch": "Amount gap",
        "sellernamemismatch": "Seller mismatch",
        "buyernamemismatch": "Buyer mismatch",
        "invoicedateearlierthanpo": "Invoice date before PO",
        "missingpo": "Missing PO",
        "purchaseordermissing": "Missing PO",
        "duplicateinvoice": "Possible duplicate",
        "duplicaterecord": "Possible duplicate",
        "taxidmismatch": "Tax ID mismatch",
    }
    if normalized in mapping:
        return mapping[normalized]
    lowered = text.lower()
    if "amount mismatch" in lowered:
        return "Amount gap"
    if "seller" in lowered and "mismatch" in lowered:
        return "Seller mismatch"
    if "buyer" in lowered and "mismatch" in lowered:
        return "Buyer mismatch"
    if "date" in lowered and "po" in lowered:
        return "Invoice date before PO"
    if "duplicate" in lowered:
        return "Possible duplicate"
    return compact_label(text)


def summarize_risk_reason(reason: Any, *, limit: int = 160, max_parts: int = 3) -> str:
    parts: List[str] = []

    def push(text: Any) -> None:
        label = risk_reason_label(text)
        if label != "-" and label not in parts and len(parts) < max_parts:
            parts.append(label)

    def walk(value: Any) -> None:
        if len(parts) >= max_parts or value in (None, ""):
            return
        decoded = decode_json(value)
        if isinstance(decoded, list):
            for item in decoded:
                walk(item)
                if len(parts) >= max_parts:
                    break
            return
        if isinstance(decoded, dict):
            for key in ("summary", "reason", "message", "rule", "type", "code"):
                if key in decoded:
                    walk(decoded.get(key))
                    if len(parts) >= max_parts:
                        break
            if not parts:
                push(json.dumps(decoded, ensure_ascii=False))
            return
        push(decoded)

    walk(reason)
    return short_text("; ".join(parts), limit=limit) if parts else "-"


def public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": safe_int(user.get("id")),
        "email": str(user.get("email") or "").strip().lower(),
        "full_name": str(user.get("full_name") or "").strip() or "Unnamed User",
        "role": str(user.get("role") or "reviewer").strip().lower(),
    }


def log_security_event(
    db: MySQLClient,
    *,
    event_type: str,
    user_id: Optional[int] = None,
    email: str = "",
    role: str = "",
    request_id: str = "",
    ip_address: str = "",
    user_agent: str = "",
    outcome: str = "info",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        db.execute(
            """
            INSERT INTO app_security_events(
              event_type, user_id, email, role, request_id, ip_address, user_agent, outcome, metadata
            )
            VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(event_type)[:64],
                int(user_id) if user_id else None,
                str(email or "").strip().lower()[:255] or None,
                str(role or "").strip().lower()[:32] or None,
                str(request_id or "")[:64] or None,
                str(ip_address or "")[:64] or None,
                str(user_agent or "")[:255] or None,
                str(outcome or "info")[:32],
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
    except Exception as exc:
        print(f"[warn] Failed to write security event {event_type}: {exc}")


def record_login_attempt(
    db: MySQLClient,
    *,
    email: str,
    ip_address: str,
    user_agent: str,
    success: bool,
    failure_reason: str = "",
    request_id: str = "",
) -> None:
    try:
        db.execute(
            """
            INSERT INTO app_login_attempts(email, ip_address, user_agent, success, failure_reason, request_id)
            VALUES(%s, %s, %s, %s, %s, %s)
            """,
            (
                str(email or "").strip().lower()[:255],
                str(ip_address or "")[:64] or None,
                str(user_agent or "")[:255] or None,
                1 if success else 0,
                str(failure_reason or "")[:64] or None,
                str(request_id or "")[:64] or None,
            ),
        )
    except Exception as exc:
        print(f"[warn] Failed to record login attempt: {exc}")


def login_is_rate_limited(db: MySQLClient, *, email: str, ip_address: str, max_attempts: int, window_sec: int) -> bool:
    row = db.fetch_one(
        """
        SELECT COUNT(*) AS failure_count
        FROM app_login_attempts
        WHERE success = 0
          AND occurred_at >= DATE_SUB(NOW(), INTERVAL %s SECOND)
          AND (email = %s OR ip_address = %s)
        """,
        (
            max(1, int(window_sec)),
            str(email or "").strip().lower(),
            str(ip_address or "")[:64],
        ),
    )
    return safe_int((row or {}).get("failure_count")) >= max(1, int(max_attempts))


def sync_snapshot(sync_row: Optional[Dict[str, Any]]) -> tuple[str, str]:
    if not sync_row:
        return "Not Synced", "warn"
    if sync_row.get("feishu_record_id") and not sync_row.get("sync_error"):
        return "Feishu Linked", "ok"
    if sync_row.get("sync_error"):
        return "Recovery Needed", "danger"
    return "Not Synced", "warn"


def serialize_invoice_list_item(row: Dict[str, Any]) -> Dict[str, Any]:
    sync_label, sync_tone = sync_snapshot(
        {
            "feishu_record_id": row.get("feishu_record_id"),
            "sync_error": row.get("sync_error"),
        }
    )
    return {
        "id": safe_int(row.get("id")),
        "invoice_date": serialize_value(row.get("invoice_date")),
        "seller_name": row.get("seller_name"),
        "buyer_name": row.get("buyer_name"),
        "invoice_code": row.get("invoice_code"),
        "invoice_number": row.get("invoice_number"),
        "purchase_order_no": row.get("purchase_order_no"),
        "total_amount_with_tax": safe_float(row.get("total_amount_with_tax")),
        "expected_amount": safe_float(row.get("expected_amount")),
        "amount_diff": safe_float(row.get("amount_diff")),
        "risk_flag": safe_int(row.get("risk_flag")) == 1,
        "risk_reason_summary": summarize_risk_reason(row.get("risk_reason")),
        "invoice_status": row.get("invoice_status"),
        "notify_personal_status": row.get("notify_personal_status"),
        "notify_leader_status": row.get("notify_leader_status"),
        "created_at": serialize_value(row.get("created_at")),
        "sync_label": sync_label,
        "sync_tone": sync_tone,
        "sync_error": short_text(row.get("sync_error"), limit=120) if row.get("sync_error") else None,
    }


def ensure_bootstrap_admin(db: MySQLClient, cfg: Dict[str, Any]) -> None:
    email = str(cfg.get("AUTH_BOOTSTRAP_ADMIN_EMAIL") or "").strip().lower()
    password = str(cfg.get("AUTH_BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
    full_name = str(cfg.get("AUTH_BOOTSTRAP_ADMIN_NAME") or "Platform Admin").strip()
    if not email or not password:
        return
    row = db.fetch_one("SELECT id FROM app_users WHERE email=%s LIMIT 1", (email,))
    if row:
        return
    db.execute(
        """
        INSERT INTO app_users(email, full_name, password_hash, role, is_active)
        VALUES(%s, %s, %s, %s, %s)
        """,
        (email, full_name, hash_password(password), "admin", 1),
    )


def get_user_by_email(db: MySQLClient, email: str) -> Optional[Dict[str, Any]]:
    normalized = str(email or "").strip().lower()
    if not normalized:
        return None
    return db.fetch_one("SELECT * FROM app_users WHERE email=%s LIMIT 1", (normalized,))


def get_user_by_id(db: MySQLClient, user_id: int) -> Optional[Dict[str, Any]]:
    return db.fetch_one("SELECT * FROM app_users WHERE id=%s LIMIT 1", (int(user_id),))


def authenticate_user(db: MySQLClient, email: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_email(db, email)
    if not user or safe_int(user.get("is_active")) != 1:
        return None
    if not verify_password(password, str(user.get("password_hash") or "")):
        return None
    return user


def touch_last_login(db: MySQLClient, user_id: int) -> None:
    db.execute("UPDATE app_users SET last_login_at=NOW(), updated_at=NOW() WHERE id=%s", (int(user_id),))


def create_refresh_session(
    db: MySQLClient,
    user_id: int,
    ttl_days: int,
    user_agent: str = "",
    ip_address: str = "",
) -> str:
    raw_token = generate_refresh_token()
    expires_at = dt.datetime.utcnow() + dt.timedelta(days=int(ttl_days))
    db.execute(
        """
        INSERT INTO app_refresh_tokens(
          user_id, token_hash, user_agent, ip_address, device_label, last_seen_at, expires_at
        )
        VALUES(%s, %s, %s, %s, %s, NOW(), %s)
        """,
        (
            int(user_id),
            hash_refresh_token(raw_token),
            str(user_agent or "")[:255] or None,
            str(ip_address or "")[:64] or None,
            device_label_from_user_agent(user_agent),
            expires_at,
        ),
    )
    touch_last_login(db, user_id)
    return raw_token


def revoke_refresh_token(db: MySQLClient, raw_token: str, reason: str = "logout") -> int:
    if not raw_token:
        return 0
    return db.execute(
        """
        UPDATE app_refresh_tokens
        SET revoked_at=NOW(), revoked_reason=%s, updated_at=NOW()
        WHERE token_hash=%s AND revoked_at IS NULL
        """,
        (str(reason or "logout")[:64], hash_refresh_token(raw_token)),
    )


def get_user_from_refresh_token(db: MySQLClient, raw_token: str) -> Optional[Dict[str, Any]]:
    if not raw_token:
        return None
    row = db.fetch_one(
        """
        SELECT u.*, t.id AS refresh_token_id
        FROM app_refresh_tokens t
        INNER JOIN app_users u ON u.id = t.user_id
        WHERE t.token_hash=%s
          AND t.revoked_at IS NULL
          AND t.expires_at > NOW()
          AND u.is_active = 1
        LIMIT 1
        """,
        (hash_refresh_token(raw_token),),
    )
    if row and row.get("refresh_token_id"):
        db.execute("UPDATE app_refresh_tokens SET last_seen_at=NOW(), updated_at=NOW() WHERE id=%s", (int(row["refresh_token_id"]),))
    return row


def list_refresh_sessions(db: MySQLClient, user_id: int) -> List[Dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT id, user_agent, ip_address, device_label, last_seen_at, expires_at, revoked_at, created_at
        FROM app_refresh_tokens
        WHERE user_id=%s
        ORDER BY COALESCE(last_seen_at, created_at) DESC, id DESC
        """,
        (int(user_id),),
    )
    return [
        {
            "id": safe_int(row.get("id")),
            "user_agent": row.get("user_agent"),
            "ip_address": row.get("ip_address"),
            "device_label": row.get("device_label") or device_label_from_user_agent(str(row.get("user_agent") or "")),
            "last_seen_at": serialize_value(row.get("last_seen_at")),
            "expires_at": serialize_value(row.get("expires_at")),
            "revoked_at": serialize_value(row.get("revoked_at")),
            "created_at": serialize_value(row.get("created_at")),
            "is_current": False,
        }
        for row in rows
    ]


def revoke_refresh_session_by_id(db: MySQLClient, *, user_id: int, session_id: int, reason: str = "user_revoked") -> int:
    return db.execute(
        """
        UPDATE app_refresh_tokens
        SET revoked_at=NOW(), revoked_reason=%s, updated_at=NOW()
        WHERE id=%s AND user_id=%s AND revoked_at IS NULL
        """,
        (str(reason or "user_revoked")[:64], int(session_id), int(user_id)),
    )


def issue_auth_payload(cfg: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    access_token, expires_at = create_access_token(
        user_id=safe_int(user.get("id")),
        email=str(user.get("email") or ""),
        role=str(user.get("role") or "reviewer"),
        full_name=str(user.get("full_name") or ""),
        secret=str(cfg.get("AUTH_JWT_SECRET") or ""),
        ttl_sec=safe_int(cfg.get("AUTH_ACCESS_TTL_SEC") or 900),
    )
    return {
        "user": public_user(user),
        "access_token": access_token,
        "expires_at": expires_at,
    }


def fetch_metrics(db: MySQLClient) -> Dict[str, Any]:
    sql = """
    SELECT
      COUNT(*) AS total_count,
      SUM(CASE WHEN risk_flag = 1 THEN 1 ELSE 0 END) AS risk_count,
      SUM(CASE WHEN invoice_status = 'Pending' THEN 1 ELSE 0 END) AS pending_count,
      SUM(CASE WHEN DATE(created_at) = CURDATE() THEN 1 ELSE 0 END) AS today_count
    FROM invoices
    """
    return db.fetch_one(sql) or {"total_count": 0, "risk_count": 0, "pending_count": 0, "today_count": 0}


def fetch_feishu_sync_summary(db: MySQLClient) -> Dict[str, Any]:
    sql = """
    SELECT
      SUM(CASE WHEN s.invoice_id IS NULL THEN 1 ELSE 0 END) AS pending_count,
      SUM(CASE WHEN s.invoice_id IS NOT NULL AND (s.feishu_record_id IS NULL OR s.sync_error IS NOT NULL) THEN 1 ELSE 0 END) AS failed_count,
      SUM(CASE WHEN s.feishu_record_id IS NOT NULL AND (s.sync_error IS NULL OR s.sync_error = '') THEN 1 ELSE 0 END) AS synced_count
    FROM invoices i
    LEFT JOIN invoice_feishu_sync s ON s.invoice_id = i.id
    """
    return db.fetch_one(sql) or {"pending_count": 0, "failed_count": 0, "synced_count": 0}


def fetch_recent_failed_feishu_syncs(db: MySQLClient, limit: int = 10) -> List[Dict[str, Any]]:
    sql = """
    SELECT
      s.invoice_id,
      i.seller_name,
      i.invoice_code,
      i.invoice_number,
      i.purchase_order_no,
      s.sync_error,
      s.updated_at
    FROM invoice_feishu_sync s
    INNER JOIN invoices i ON i.id = s.invoice_id
    WHERE s.feishu_record_id IS NULL OR s.sync_error IS NOT NULL
    ORDER BY s.updated_at DESC, s.id DESC
    LIMIT %s
    """
    rows = db.fetch_all(sql, (int(limit),))
    for row in rows:
        row["updated_at"] = serialize_value(row.get("updated_at"))
        row["sync_error"] = short_text(row.get("sync_error"), limit=180)
    return rows


def fetch_recent_invoices(db: MySQLClient, limit: int = 100) -> List[Dict[str, Any]]:
    sql = """
    SELECT
      i.id, i.invoice_date, i.seller_name, i.buyer_name, i.invoice_code, i.invoice_number, i.purchase_order_no,
      i.total_amount_with_tax, i.expected_amount, i.amount_diff, i.risk_flag, i.invoice_status, i.risk_reason,
      i.notify_personal_status, i.notify_leader_status, i.created_at,
      s.feishu_record_id, s.sync_error
    FROM invoices i
    LEFT JOIN invoice_feishu_sync s ON s.invoice_id = i.id
    ORDER BY i.id DESC
    LIMIT %s
    """
    rows = db.fetch_all(sql, (int(limit),))
    for row in rows:
        row["risk_reason"] = decode_json(row.get("risk_reason"))
    return rows


def fetch_daily_activity(db: MySQLClient) -> List[Dict[str, Any]]:
    sql = """
    SELECT
      DATE(created_at) AS activity_date,
      COUNT(*) AS total_count,
      SUM(CASE WHEN risk_flag = 1 THEN 1 ELSE 0 END) AS risk_count
    FROM invoices
    WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
    GROUP BY DATE(created_at)
    ORDER BY DATE(created_at) ASC
    """
    rows = db.fetch_all(sql)
    for row in rows:
        row["activity_date"] = serialize_value(row.get("activity_date"))
        row["day_label"] = fmt_day_label(row.get("activity_date"))
    return rows


def fetch_purchase_order(db: MySQLClient, purchase_order_no: str) -> Optional[Dict[str, Any]]:
    purchase_no = str(purchase_order_no or "").strip()
    if not purchase_no:
        return None
    row = db.fetch_one("SELECT * FROM purchase_orders WHERE purchase_no=%s LIMIT 1", (purchase_no,))
    return serialize_value(row) if row else None


def fetch_invoice_detail(db: MySQLClient, invoice_id: int) -> Optional[Dict[str, Any]]:
    invoice = db.fetch_one("SELECT * FROM invoices WHERE id=%s", (int(invoice_id),))
    if not invoice:
        return None

    items = db.fetch_all("SELECT * FROM invoice_items WHERE invoice_id=%s ORDER BY id ASC", (int(invoice_id),))
    events = db.fetch_all("SELECT * FROM invoice_events WHERE invoice_id=%s ORDER BY id DESC", (int(invoice_id),))
    sync_row = db.fetch_one("SELECT * FROM invoice_feishu_sync WHERE invoice_id=%s", (int(invoice_id),))
    review_tasks = db.fetch_all(
        """
        SELECT * FROM invoice_review_tasks
        WHERE invoice_id=%s
        ORDER BY id DESC
        """,
        (int(invoice_id),),
    )
    transitions = db.fetch_all(
        """
        SELECT *
        FROM invoice_state_transitions
        WHERE invoice_id=%s
        ORDER BY id DESC
        """,
        (int(invoice_id),),
    )

    invoice["raw_ocr_json"] = decode_json(invoice.get("raw_ocr_json"))
    invoice["llm_json"] = decode_json(invoice.get("llm_json"))
    invoice["risk_reason"] = decode_json(invoice.get("risk_reason"))
    invoice["risk_reason_summary"] = summarize_risk_reason(invoice.get("risk_reason"))
    sync_label, sync_tone = sync_snapshot(sync_row)

    return {
        "invoice": serialize_value(invoice),
        "items": [serialize_value(row) for row in items],
        "events": [serialize_value({**row, "payload": decode_json(row.get("payload"))}) for row in events],
        "review_tasks": [serialize_value(row) for row in review_tasks],
        "state_transitions": [serialize_value(row) for row in transitions],
        "sync": serialize_value(
            {
                "feishu_record_id": sync_row.get("feishu_record_id") if sync_row else None,
                "synced_at": sync_row.get("synced_at") if sync_row else None,
                "sync_error": sync_row.get("sync_error") if sync_row else None,
                "sync_label": sync_label,
                "sync_tone": sync_tone,
            }
        ),
        "purchase_order": fetch_purchase_order(db, str(invoice.get("purchase_order_no") or "")),
    }


def latest_duplicate_review_task(
    db: MySQLClient,
    *,
    invoice_id: int,
    review_result: str,
    handler_user: str,
    handling_note: str,
) -> Optional[Dict[str, Any]]:
    return db.fetch_one(
        """
        SELECT id
        FROM invoice_review_tasks
        WHERE invoice_id=%s
          AND review_result=%s
          AND COALESCE(handler_user, '')=%s
          AND COALESCE(handling_note, '')=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(invoice_id), review_result, handler_user or "", handling_note or ""),
    )


def update_invoice_review(
    db: MySQLClient,
    *,
    invoice_id: int,
    purchase_order_no: str,
    unique_hash: str,
    handler_user: str,
    handler_reason: str,
    invoice_status: str,
    actor_user: Dict[str, Any],
    request_id: str = "",
    idempotency_key: str = "",
    ) -> bool:
    invoice_row = db.fetch_one("SELECT invoice_status FROM invoices WHERE id=%s LIMIT 1", (int(invoice_id),)) or {}
    current_status = str(invoice_row.get("invoice_status") or "")
    actor_role = str(actor_user.get("role") or "").strip().lower()
    duplicate = latest_duplicate_review_task(
        db,
        invoice_id=invoice_id,
        review_result=invoice_status,
        handler_user=handler_user,
        handling_note=handler_reason,
    )
    if duplicate and current_status == invoice_status:
        return False
    validate_review_transition(current_status, invoice_status, actor_role)

    db.execute(
        """
        UPDATE invoices
        SET invoice_status=%s, handler_user=%s, handler_reason=%s, handled_at=NOW(), updated_at=NOW()
        WHERE id=%s
        """,
        (invoice_status, handler_user or None, handler_reason or None, int(invoice_id)),
    )
    db.execute(
        """
        INSERT INTO invoice_review_tasks(
          invoice_id, purchase_order_no, unique_hash, review_result, handler_user, handling_note, source_channel
        )
        VALUES(%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            int(invoice_id),
            purchase_order_no or None,
            unique_hash or None,
            invoice_status,
            handler_user or None,
            handler_reason or None,
            "web_app",
        ),
    )
    db.execute(
        """
        INSERT INTO invoice_state_transitions(
          invoice_id, from_status, to_status, actor_user_id, actor_email, actor_role,
          request_id, reason, idempotency_key
        )
        VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            int(invoice_id),
            current_status or None,
            invoice_status,
            safe_int(actor_user.get("id")) or None,
            str(actor_user.get("email") or "")[:255] or None,
            actor_role or None,
            str(request_id or "")[:64] or None,
            handler_reason or None,
            str(idempotency_key or "")[:128] or uuid.uuid4().hex,
        ),
    )
    payload = json.dumps(
        {
            "purchase_order_no": purchase_order_no,
            "unique_hash": unique_hash,
            "handler_user": handler_user,
            "handler_reason": handler_reason,
            "invoice_status": invoice_status,
            "previous_status": current_status or None,
            "request_id": request_id or None,
        },
        ensure_ascii=False,
    )
    db.execute(
        "INSERT INTO invoice_events(invoice_id, event_type, event_status, payload) VALUES(%s, %s, %s, %s)",
        (int(invoice_id), "WORK_ORDER_SUBMITTED", invoice_status, payload),
    )
    return True


def _unknown_connector_rows() -> List[Dict[str, Any]]:
    return [
        {
            "name": name,
            "status": "UNKNOWN",
            "message": "Health check has not been refreshed yet. Open Ops Center to run a live check.",
            "detail": None,
            "cached_at": None,
            "latency_ms": None,
            "stale": True,
        }
        for name in CONNECTOR_NAMES
    ]


def connector_status_snapshot(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    with _CONNECTOR_CACHE_LOCK:
        rows = list(_CONNECTOR_CACHE.get("rows") or [])
        expires_at = float(_CONNECTOR_CACHE.get("expires_at") or 0.0)
    if not rows:
        return _unknown_connector_rows()
    stale = time.time() >= expires_at
    return [{**row, "stale": stale} for row in rows]


def integration_status(cfg: Dict[str, Any], *, force_refresh: bool = False) -> List[Dict[str, Any]]:
    ttl_sec = max(5, safe_int(cfg.get("CONNECTOR_HEALTH_TTL_SEC") or 60))
    with _CONNECTOR_CACHE_LOCK:
        cached_rows = list(_CONNECTOR_CACHE.get("rows") or [])
        expires_at = float(_CONNECTOR_CACHE.get("expires_at") or 0.0)
    if cached_rows and not force_refresh and time.time() < expires_at:
        return [{**row, "stale": False} for row in cached_rows]

    check_fns = [
        lambda: check_http_endpoint("OCR", f"{cfg['ocr_base_url'].rstrip('/')}/docs"),
        lambda: check_dify(cfg["dify_base_url"], cfg["dify_api_key"], cfg["dify_workflow_id"]),
        lambda: check_feishu(
            cfg["feishu_app_id"],
            cfg["feishu_app_secret"],
            cfg["bitable_app_token"],
            cfg["bitable_table_id"],
        ),
        lambda: check_smtp(
            cfg["SMTP_HOST"],
            int(cfg["SMTP_PORT"]),
            cfg["SMTP_USER"],
            cfg["SMTP_PASS"],
            bool(cfg["SMTP_USE_TLS"]),
            bool(cfg["SMTP_USE_SSL"]),
            cfg["SMTP_FROM_NAME"],
            cfg["SMTP_FROM_EMAIL"],
        ),
    ]
    rows: List[Dict[str, Any]] = []
    cached_at = iso_utc()
    for check_fn in check_fns:
        started_at = time.perf_counter()
        check = check_fn()
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        status = "OK" if check.ok else "NOT READY"
        rows.append(
            {
                "name": check.name,
                "status": status,
                "message": str(check.message or "").strip(),
                "detail": str(check.detail or "").strip() or None,
                "cached_at": cached_at,
                "latency_ms": latency_ms,
                "stale": False,
            }
        )
    with _CONNECTOR_CACHE_LOCK:
        _CONNECTOR_CACHE["rows"] = rows
        _CONNECTOR_CACHE["cached_at"] = cached_at
        _CONNECTOR_CACHE["expires_at"] = time.time() + ttl_sec
    return rows


def feishu_retry_worker_summary(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "enabled": bool(cfg.get("FEISHU_RETRY_WORKER_ENABLED")),
        "interval_sec": safe_int(cfg.get("FEISHU_RETRY_INTERVAL_SEC")),
        "mode": str(cfg.get("FEISHU_RETRY_MODE") or "failed"),
        "limit": safe_int(cfg.get("FEISHU_RETRY_BATCH_LIMIT")),
    }


def build_dashboard_summary(db: MySQLClient, cfg: Dict[str, Any]) -> Dict[str, Any]:
    metrics = fetch_metrics(db)
    invoices = fetch_recent_invoices(db, limit=16)
    feishu_sync = fetch_feishu_sync_summary(db)
    connectors = connector_status_snapshot(cfg)

    total_amount = sum(safe_float(row.get("total_amount_with_tax")) for row in invoices)
    risk_amount = sum(abs(safe_float(row.get("amount_diff"))) for row in invoices if safe_int(row.get("risk_flag")) == 1)
    total_count = safe_int(metrics.get("total_count"))
    risk_count = safe_int(metrics.get("risk_count"))
    pending_count = safe_int(metrics.get("pending_count"))
    synced_count = safe_int(feishu_sync.get("synced_count"))
    failed_count = safe_int(feishu_sync.get("failed_count"))
    alert_sent_count = sum(
        1
        for row in invoices
        if safe_int(row.get("risk_flag")) == 1 and str(row.get("notify_personal_status") or "").strip().lower() == "sent"
    )
    risk_rows = sorted(
        [row for row in invoices if safe_int(row.get("risk_flag")) == 1],
        key=lambda row: abs(safe_float(row.get("amount_diff"))),
        reverse=True,
    )
    risk_ratio = (risk_count / total_count) if total_count else 0.0
    sync_ratio = (synced_count / total_count) if total_count else 0.0
    reviewed_ratio = ((total_count - pending_count) / total_count) if total_count else 0.0
    alert_ratio = (alert_sent_count / risk_count) if risk_count else 1.0
    ready_count = sum(1 for row in connectors if row["status"] == "OK")

    return {
        "totals": {
            "total_count": total_count,
            "risk_count": risk_count,
            "pending_count": pending_count,
            "today_count": safe_int(metrics.get("today_count")),
            "total_amount": total_amount,
            "risk_amount": risk_amount,
        },
        "ratios": {
            "risk_ratio": risk_ratio,
            "reviewed_ratio": reviewed_ratio,
            "sync_ratio": sync_ratio,
            "alert_ratio": alert_ratio,
        },
        "connectors": {
            "ready_count": ready_count,
            "total_count": len(connectors),
            "blocked_count": max(len(connectors) - ready_count, 0),
        },
        "feishu_sync": {
            "pending_count": safe_int(feishu_sync.get("pending_count")),
            "failed_count": failed_count,
            "synced_count": synced_count,
        },
        "top_risk": [serialize_invoice_list_item(row) for row in risk_rows[:4]],
        "recent_queue": [serialize_invoice_list_item(row) for row in invoices[:6]],
    }


def build_dashboard_activity(db: MySQLClient) -> List[Dict[str, Any]]:
    return [serialize_value(row) for row in fetch_daily_activity(db)]


def _build_invoice_filters(*, search: str = "", status: str = "All", risk_only: bool = False) -> tuple[str, List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    keyword = str(search or "").strip().lower()
    if keyword:
        like = f"%{keyword}%"
        clauses.append(
            """
            (
              LOWER(COALESCE(i.seller_name, '')) LIKE %s
              OR LOWER(COALESCE(i.buyer_name, '')) LIKE %s
              OR LOWER(COALESCE(i.invoice_number, '')) LIKE %s
              OR LOWER(COALESCE(i.invoice_code, '')) LIKE %s
              OR LOWER(COALESCE(i.purchase_order_no, '')) LIKE %s
            )
            """
        )
        params.extend([like, like, like, like, like])
    normalized_status = str(status or "All").strip()
    if normalized_status and normalized_status != "All":
        clauses.append("i.invoice_status = %s")
        params.append(normalized_status)
    if risk_only:
        clauses.append("i.risk_flag = 1")
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def list_invoices(
    db: MySQLClient,
    *,
    search: str = "",
    status: str = "All",
    risk_only: bool = False,
    sort: str = "newest",
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    where_sql, params = _build_invoice_filters(search=search, status=status, risk_only=risk_only)
    sort_sql = {
        "risk": "ORDER BY i.risk_flag DESC, ABS(COALESCE(i.amount_diff, 0)) DESC, i.id DESC",
        "largest_delta": "ORDER BY ABS(COALESCE(i.amount_diff, 0)) DESC, i.id DESC",
        "newest": "ORDER BY COALESCE(i.invoice_date, DATE(i.created_at)) DESC, i.id DESC",
    }.get(sort, "ORDER BY COALESCE(i.invoice_date, DATE(i.created_at)) DESC, i.id DESC")
    data_sql = f"""
    SELECT
      i.id, i.invoice_date, i.seller_name, i.buyer_name, i.invoice_code, i.invoice_number, i.purchase_order_no,
      i.total_amount_with_tax, i.expected_amount, i.amount_diff, i.risk_flag, i.invoice_status, i.risk_reason,
      i.notify_personal_status, i.notify_leader_status, i.created_at,
      s.feishu_record_id, s.sync_error
    FROM invoices i
    LEFT JOIN invoice_feishu_sync s ON s.invoice_id = i.id
    {where_sql}
    {sort_sql}
    LIMIT %s OFFSET %s
    """
    rows = db.fetch_all(data_sql, tuple(params + [int(limit), int(offset)]))
    aggregate_sql = f"""
    SELECT
      COUNT(*) AS total_count,
      SUM(CASE WHEN i.risk_flag = 1 THEN 1 ELSE 0 END) AS matched_risk_count,
      SUM(CASE WHEN i.invoice_status = 'Pending' THEN 1 ELSE 0 END) AS matched_pending_count,
      SUM(COALESCE(i.total_amount_with_tax, 0)) AS matched_total_amount
    FROM invoices i
    {where_sql}
    """
    summary = db.fetch_one(aggregate_sql, tuple(params)) or {}
    for row in rows:
        row["risk_reason"] = decode_json(row.get("risk_reason"))
    return {
        "items": [serialize_invoice_list_item(row) for row in rows],
        "total_count": safe_int(summary.get("total_count")),
        "matched_risk_count": safe_int(summary.get("matched_risk_count")),
        "matched_pending_count": safe_int(summary.get("matched_pending_count")),
        "matched_total_amount": safe_float(summary.get("matched_total_amount")),
    }


def build_ops_sync_summary(db: MySQLClient, cfg: Dict[str, Any]) -> Dict[str, Any]:
    sync_summary = fetch_feishu_sync_summary(db)
    worker = feishu_retry_worker_summary(cfg)
    return {
        "summary": {
            "pending_count": safe_int(sync_summary.get("pending_count")),
            "failed_count": safe_int(sync_summary.get("failed_count")),
            "synced_count": safe_int(sync_summary.get("synced_count")),
        },
        "retry_worker_enabled": bool(worker["enabled"]),
        "retry_interval_sec": safe_int(worker["interval_sec"]),
        "retry_mode": str(worker["mode"]),
        "retry_batch_limit": safe_int(worker["limit"]),
    }


def retry_feishu_sync(
    db: MySQLClient,
    cfg: Dict[str, Any],
    *,
    mode: str,
    limit: int,
    invoice_ids: Sequence[int],
) -> Dict[str, Any]:
    acquired = _FEISHU_RETRY_LOCK.acquire(blocking=False)
    if not acquired:
        raise RetryAlreadyRunning("A Feishu replay is already running. Wait for it to finish before retrying.")
    started_at = time.perf_counter()
    try:
        ok_count, fail_count, details = sync_invoices_to_feishu(
            db,
            cfg,
            mode=mode,
            limit=int(limit),
            invoice_ids=invoice_ids,
        )
    finally:
        _FEISHU_RETRY_LOCK.release()
    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    for detail in details:
        invoice_id = safe_int((detail or {}).get("invoice_id"))
        if not invoice_id:
            continue
        payload = json.dumps(
            {
                "mode": mode,
                "ok": bool((detail or {}).get("ok")),
                "record_id": (detail or {}).get("record_id"),
                "error": serialize_value((detail or {}).get("error")),
                "latency_ms": latency_ms,
            },
            ensure_ascii=False,
        )
        db.execute(
            "INSERT INTO invoice_events(invoice_id, event_type, event_status, payload) VALUES(%s, %s, %s, %s)",
            (invoice_id, "FEISHU_RETRY", "OK" if (detail or {}).get("ok") else "FAILED", payload),
        )
    return {
        "ok_count": safe_int(ok_count),
        "fail_count": safe_int(fail_count),
        "details": [serialize_value(item) for item in details],
    }
