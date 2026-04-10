from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from src.db.mysql_client import MySQLClient


def _json_dump(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


class MigrationRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def ensure_table(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              id BIGINT NOT NULL AUTO_INCREMENT,
              name VARCHAR(255) NOT NULL,
              applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (id),
              UNIQUE KEY uq_schema_migrations_name (name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )

    def has_migration(self, name: str) -> bool:
        row = self.db.fetch_one("SELECT id FROM schema_migrations WHERE name=%s LIMIT 1", (name,))
        return bool(row)

    def mark_applied(self, name: str) -> None:
        self.db.execute("INSERT INTO schema_migrations(name) VALUES(%s)", (name,))


class UserRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def find_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        return self.db.fetch_one(
            "SELECT * FROM users WHERE username=%s AND is_active=1 LIMIT 1",
            (username,),
        )

    def seed_user(self, username: str, password_hash: str, role: str) -> None:
        self.db.execute(
            """
            INSERT INTO users(username, password_hash, role, is_active)
            VALUES(%s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
              password_hash=VALUES(password_hash),
              role=VALUES(role),
              is_active=1,
              updated_at=NOW()
            """,
            (username, password_hash, role),
        )

    def create_session(self, user_id: int, token: str, expires_at: str) -> None:
        self.db.execute(
            """
            INSERT INTO user_sessions(user_id, token, expires_at)
            VALUES(%s, %s, %s)
            """,
            (user_id, token, expires_at),
        )

    def find_session(self, token: str) -> Optional[Dict[str, Any]]:
        return self.db.fetch_one(
            """
            SELECT s.*, u.username, u.role, u.is_active
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token=%s AND s.revoked_at IS NULL AND s.expires_at > UTC_TIMESTAMP()
            LIMIT 1
            """,
            (token,),
        )

    def touch_session(self, token: str) -> None:
        self.db.execute("UPDATE user_sessions SET last_used_at=UTC_TIMESTAMP() WHERE token=%s", (token,))


class FileRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def find_by_sha256(self, sha256: str) -> Optional[Dict[str, Any]]:
        return self.db.fetch_one("SELECT * FROM invoice_files WHERE sha256=%s LIMIT 1", (sha256,))

    def get(self, file_id: int) -> Optional[Dict[str, Any]]:
        return self.db.fetch_one("SELECT * FROM invoice_files WHERE id=%s LIMIT 1", (file_id,))

    def create(
        self,
        *,
        original_name: str,
        storage_path: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        uploaded_by: str,
        source_type: str = "api_upload",
    ) -> int:
        return self.db.execute_returning_id(
            """
            INSERT INTO invoice_files(
              file_name, original_name, mime_type, size_bytes, sha256,
              storage_path, uploaded_by, source_type
            )
            VALUES(%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                storage_path.split("/")[-1],
                original_name,
                mime_type,
                size_bytes,
                sha256,
                storage_path,
                uploaded_by,
                source_type,
            ),
        )


class TaskRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def create(self, file_id: int, created_by: str, task_type: str = "INGEST") -> Dict[str, Any]:
        trace_id = str(uuid.uuid4())
        task_id = self.db.execute_returning_id(
            """
            INSERT INTO invoice_tasks(
              invoice_file_id, task_type, processing_status, retry_count, trace_id, created_by
            )
            VALUES(%s, %s, 'PENDING', 0, %s, %s)
            """,
            (file_id, task_type, trace_id, created_by),
        )
        return self.get(task_id)

    def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        return self.db.fetch_one("SELECT * FROM invoice_tasks WHERE id=%s LIMIT 1", (task_id,))

    def list(self, *, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM invoice_tasks"
        params: List[Any] = []
        if status:
            sql += " WHERE processing_status=%s"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT %s"
        params.append(int(limit))
        return self.db.fetch_all(sql, tuple(params))

    def find_open_by_file_id(self, file_id: int) -> Optional[Dict[str, Any]]:
        return self.db.fetch_one(
            """
            SELECT * FROM invoice_tasks
            WHERE invoice_file_id=%s AND processing_status IN ('PENDING','RUNNING')
            ORDER BY id DESC LIMIT 1
            """,
            (file_id,),
        )

    def claim_next(self, worker_id: str) -> Optional[Dict[str, Any]]:
        task = self.db.fetch_one(
            """
            SELECT * FROM invoice_tasks
            WHERE processing_status='PENDING'
            ORDER BY id ASC
            LIMIT 1
            """
        )
        if not task:
            return None
        updated = self.db.execute(
            """
            UPDATE invoice_tasks
            SET processing_status='RUNNING',
                worker_id=%s,
                started_at=UTC_TIMESTAMP(),
                updated_at=UTC_TIMESTAMP()
            WHERE id=%s AND processing_status='PENDING'
            """,
            (worker_id, task["id"]),
        )
        if updated == 0:
            return None
        return self.get(int(task["id"]))

    def mark_completed(self, task_id: int, invoice_id: int) -> None:
        self.db.execute(
            """
            UPDATE invoice_tasks
            SET invoice_id=%s,
                processing_status='COMPLETED',
                error_code=NULL,
                error_message=NULL,
                finished_at=UTC_TIMESTAMP(),
                updated_at=UTC_TIMESTAMP()
            WHERE id=%s
            """,
            (invoice_id, task_id),
        )

    def mark_failed(self, task_id: int, error_code: str, error_message: str) -> None:
        self.db.execute(
            """
            UPDATE invoice_tasks
            SET processing_status='FAILED',
                error_code=%s,
                error_message=%s,
                finished_at=UTC_TIMESTAMP(),
                updated_at=UTC_TIMESTAMP()
            WHERE id=%s
            """,
            (error_code[:64], error_message[:4000], task_id),
        )

    def retry(self, task_id: int) -> None:
        self.db.execute(
            """
            UPDATE invoice_tasks
            SET processing_status='PENDING',
                retry_count=retry_count+1,
                error_code=NULL,
                error_message=NULL,
                worker_id=NULL,
                started_at=NULL,
                finished_at=NULL,
                updated_at=UTC_TIMESTAMP()
            WHERE id=%s
            """,
            (task_id,),
        )


class ProductInvoiceRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def find_by_unique_hash(self, unique_hash: str) -> Optional[Dict[str, Any]]:
        return self.db.fetch_one("SELECT * FROM invoices WHERE unique_hash=%s LIMIT 1", (unique_hash,))

    def get(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        return self.db.fetch_one("SELECT * FROM invoices WHERE id=%s LIMIT 1", (invoice_id,))

    def list(self, *, q: str = "", review_status: str = "", processing_status: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        sql = """
        SELECT id, processing_status, review_status, seller_name, invoice_number,
               purchase_order_no, total_amount_with_tax, risk_flag, confidence_overall, created_at
        FROM invoices
        WHERE 1=1
        """
        params: List[Any] = []
        if q:
            sql += " AND (seller_name LIKE %s OR invoice_number LIKE %s OR purchase_order_no LIKE %s)"
            like = f"%{q}%"
            params.extend([like, like, like])
        if review_status:
            sql += " AND review_status=%s"
            params.append(review_status)
        if processing_status:
            sql += " AND processing_status=%s"
            params.append(processing_status)
        sql += " ORDER BY id DESC LIMIT %s"
        params.append(int(limit))
        return self.db.fetch_all(sql, tuple(params))

    def insert_invoice(self, row: Dict[str, Any]) -> int:
        sql = """
        INSERT INTO invoices(
          invoice_type, invoice_code, invoice_number, invoice_date, check_code, machine_code,
          invoice_status, processing_status, review_status, is_red_invoice, red_invoice_ref,
          seller_name, seller_tax_id, seller_address, seller_phone, seller_bank, seller_bank_account,
          buyer_name, buyer_tax_id, buyer_address, buyer_phone, buyer_bank, buyer_bank_account,
          total_amount_without_tax, total_tax_amount, total_amount_with_tax, amount_in_words,
          drawer, reviewer, payee, remarks, purchase_order_no, source_file_path,
          raw_ocr_json, llm_json, schema_version, expected_amount, amount_diff, risk_flag, risk_reason,
          handler_user, handler_reason, handled_at, source_file_id, current_task_id, latest_extraction_id,
          confidence_overall, unique_hash
        )
        VALUES(
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,%s,
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,%s,%s,
          %s,%s
        )
        """
        params = (
            row.get("invoice_type"), row.get("invoice_code"), row.get("invoice_number"), row.get("invoice_date"),
            row.get("check_code"), row.get("machine_code"),
            row.get("invoice_status", "Pending"),
            row.get("processing_status", "COMPLETED"),
            row.get("review_status", "PENDING"),
            row.get("is_red_invoice", 0), row.get("red_invoice_ref"),
            row.get("seller_name"), row.get("seller_tax_id"), row.get("seller_address"), row.get("seller_phone"),
            row.get("seller_bank"), row.get("seller_bank_account"),
            row.get("buyer_name"), row.get("buyer_tax_id"), row.get("buyer_address"), row.get("buyer_phone"),
            row.get("buyer_bank"), row.get("buyer_bank_account"),
            row.get("total_amount_without_tax"), row.get("total_tax_amount"), row.get("total_amount_with_tax"),
            row.get("amount_in_words"),
            row.get("drawer"), row.get("reviewer"), row.get("payee"), row.get("remarks"),
            row.get("purchase_order_no"), row.get("source_file_path"),
            _json_dump(row.get("raw_ocr_json")),
            _json_dump(row.get("llm_json")),
            row.get("schema_version", "v1"),
            row.get("expected_amount"), row.get("amount_diff"), row.get("risk_flag", 0),
            _json_dump(row.get("risk_reason") or []),
            row.get("handler_user"), row.get("handler_reason"), row.get("handled_at"),
            row.get("source_file_id"), row.get("current_task_id"), row.get("latest_extraction_id"),
            row.get("confidence_overall"), row["unique_hash"],
        )
        return self.db.execute_returning_id(sql, params)

    def insert_items(self, invoice_id: int, items: List[Dict[str, Any]]) -> int:
        if not items:
            return 0
        return self.db.executemany(
            """
            INSERT INTO invoice_items(
              invoice_id, item_name, item_spec, item_unit, item_quantity,
              item_unit_price, item_amount, tax_rate, tax_amount
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    invoice_id,
                    item.get("item_name"),
                    item.get("item_spec"),
                    item.get("item_unit"),
                    item.get("item_quantity"),
                    item.get("item_unit_price"),
                    item.get("item_amount"),
                    item.get("tax_rate"),
                    item.get("tax_amount"),
                )
                for item in items
            ],
        )

    def update_processing(self, invoice_id: int, *, processing_status: str, review_status: str, current_task_id: int, confidence_overall: float) -> None:
        invoice_status = {
            "PENDING": "Pending",
            "NEEDS_REVIEW": "NeedsReview",
            "APPROVED": "Approved",
            "REJECTED": "Rejected",
        }.get(review_status, "Pending")
        self.db.execute(
            """
            UPDATE invoices
            SET processing_status=%s,
                review_status=%s,
                invoice_status=%s,
                current_task_id=%s,
                confidence_overall=%s,
                updated_at=UTC_TIMESTAMP()
            WHERE id=%s
            """,
            (processing_status, review_status, invoice_status, current_task_id, confidence_overall, invoice_id),
        )

    def finalize_review(self, invoice_id: int, *, review_status: str, handler_user: str, handler_reason: str) -> None:
        invoice_status = {
            "PENDING": "Pending",
            "NEEDS_REVIEW": "NeedsReview",
            "APPROVED": "Approved",
            "REJECTED": "Rejected",
        }.get(review_status, "Pending")
        self.db.execute(
            """
            UPDATE invoices
            SET review_status=%s,
                invoice_status=%s,
                handler_user=%s,
                handler_reason=%s,
                handled_at=UTC_TIMESTAMP(),
                updated_at=UTC_TIMESTAMP()
            WHERE id=%s
            """,
            (review_status, invoice_status, handler_user, handler_reason, invoice_id),
        )

    def summary(self) -> Dict[str, Any]:
        invoices = self.db.fetch_one(
            """
            SELECT
              COUNT(*) AS total_invoices,
              SUM(CASE WHEN review_status='NEEDS_REVIEW' THEN 1 ELSE 0 END) AS review_queue,
              SUM(CASE WHEN risk_flag=1 THEN 1 ELSE 0 END) AS risk_invoices
            FROM invoices
            """
        ) or {}
        tasks = self.db.fetch_one(
            """
            SELECT
              SUM(CASE WHEN processing_status='PENDING' THEN 1 ELSE 0 END) AS pending_tasks,
              SUM(CASE WHEN processing_status='FAILED' THEN 1 ELSE 0 END) AS failed_tasks
            FROM invoice_tasks
            """
        ) or {}
        return {**invoices, **tasks}

    def detail(self, invoice_id: int) -> Dict[str, Any]:
        invoice = self.db.fetch_one("SELECT * FROM invoices WHERE id=%s", (invoice_id,)) or {}
        items = self.db.fetch_all("SELECT * FROM invoice_items WHERE invoice_id=%s ORDER BY id ASC", (invoice_id,))
        events = self.db.fetch_all("SELECT * FROM invoice_events WHERE invoice_id=%s ORDER BY id DESC", (invoice_id,))
        extractions = self.db.fetch_all("SELECT * FROM invoice_extractions WHERE invoice_id=%s ORDER BY id DESC", (invoice_id,))
        reviews = self.db.fetch_all("SELECT * FROM invoice_review_actions WHERE invoice_id=%s ORDER BY id DESC", (invoice_id,))
        notifications = self.db.fetch_all(
            "SELECT * FROM notification_deliveries WHERE invoice_id=%s ORDER BY id DESC",
            (invoice_id,),
        )
        file_row = None
        if invoice.get("source_file_id"):
            file_row = self.db.fetch_one("SELECT * FROM invoice_files WHERE id=%s", (invoice["source_file_id"],))
        for row in [invoice, *events, *extractions, *reviews, *notifications]:
            if row and row.get("payload") and isinstance(row["payload"], str):
                try:
                    row["payload"] = json.loads(row["payload"])
                except Exception:
                    pass
        for extraction in extractions:
            for key in ("confidence_by_field", "raw_response", "normalized_schema"):
                value = extraction.get(key)
                if isinstance(value, str):
                    try:
                        extraction[key] = json.loads(value)
                    except Exception:
                        pass
        if isinstance(invoice.get("risk_reason"), str):
            try:
                invoice["risk_reason"] = json.loads(invoice["risk_reason"])
            except Exception:
                pass
        for key in ("raw_ocr_json", "llm_json"):
            value = invoice.get(key)
            if isinstance(value, str):
                try:
                    invoice[key] = json.loads(value)
                except Exception:
                    pass
        return {
            "invoice": invoice,
            "items": items,
            "events": events,
            "extractions": extractions,
            "reviews": reviews,
            "notifications": notifications,
            "file": file_row,
        }


class ExtractionRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def create(
        self,
        *,
        invoice_id: int,
        task_id: int,
        provider: str,
        model_name: str,
        model_version: str,
        prompt_version: str,
        fallback_source: str,
        confidence_overall: float,
        confidence_by_field: Dict[str, Any],
        raw_response: Dict[str, Any],
        normalized_schema: Dict[str, Any],
    ) -> int:
        return self.db.execute_returning_id(
            """
            INSERT INTO invoice_extractions(
              invoice_id, task_id, provider, model_name, model_version, prompt_version,
              fallback_source, confidence_overall, confidence_by_field, raw_response, normalized_schema
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                invoice_id,
                task_id,
                provider,
                model_name,
                model_version,
                prompt_version,
                fallback_source,
                confidence_overall,
                _json_dump(confidence_by_field),
                _json_dump(raw_response),
                _json_dump(normalized_schema),
            ),
        )


class ReviewRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def create_action(self, *, invoice_id: int, action_type: str, review_status: str, actor_user_id: int, actor_username: str, note: str, payload: Dict[str, Any]) -> int:
        return self.db.execute_returning_id(
            """
            INSERT INTO invoice_review_actions(
              invoice_id, action_type, review_status, actor_user_id, actor_username, note, payload
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s)
            """,
            (invoice_id, action_type, review_status, actor_user_id, actor_username, note, _json_dump(payload)),
        )


class EventRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def add(self, *, invoice_id: int, event_type: str, event_status: str, payload: Dict[str, Any]) -> int:
        return self.db.execute_returning_id(
            """
            INSERT INTO invoice_events(invoice_id, event_type, event_status, payload)
            VALUES(%s,%s,%s,%s)
            """,
            (invoice_id, event_type, event_status, _json_dump(payload)),
        )


class NotificationRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def record(
        self,
        *,
        invoice_id: int,
        delivery_type: str,
        channel: str,
        recipient: str,
        cc: List[str],
        status: str,
        subject: str,
        payload: Dict[str, Any],
        error_message: str = "",
    ) -> int:
        return self.db.execute_returning_id(
            """
            INSERT INTO notification_deliveries(
              invoice_id, delivery_type, channel, recipient, cc, status, subject, payload, error_message,
              delivered_at
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,
                   CASE WHEN %s='SENT' THEN UTC_TIMESTAMP() ELSE NULL END)
            """,
            (
                invoice_id,
                delivery_type,
                channel,
                recipient,
                _json_dump(cc),
                status,
                subject,
                _json_dump(payload),
                error_message[:4000],
                status,
            ),
        )
