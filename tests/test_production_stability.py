from __future__ import annotations

import datetime as dt
import json

import pytest

from src.db import mysql_client as mysql_mod
from src.api import services
from src.api.state_machine import InvalidStateTransition
from src.api.services import acquire_operation_lock, release_operation_lock, update_invoice_review
from src.services import ingestion_service as ingestion_mod
from src.services.ingestion_service import IngestionService


class ReviewFakeDB:
    def __init__(self, status: str = "Pending"):
        self.invoice_status = status
        self.tasks: list[dict] = []
        self.transitions: list[dict] = []
        self.events: list[dict] = []
        self.begun = 0
        self.committed = 0
        self.rolled_back = 0

    def begin(self):
        self.begun += 1

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def fetch_one(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        params = params or ()
        if "from invoice_review_tasks" in text and "idempotency_key=%s" in text:
            key = params[0]
            return next((task for task in self.tasks if task.get("idempotency_key") == key), None)
        if "from invoice_review_tasks" in text:
            invoice_id, review_result, handler_user, handling_note = params
            return next(
                (
                    {"id": task["id"]}
                    for task in reversed(self.tasks)
                    if task["invoice_id"] == invoice_id
                    and task["review_result"] == review_result
                    and (task.get("handler_user") or "") == handler_user
                    and (task.get("handling_note") or "") == handling_note
                ),
                None,
            )
        if "from invoices" in text:
            return {"invoice_status": self.invoice_status}
        return None

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        params = params or ()
        if text.startswith("update invoices"):
            self.invoice_status = params[0]
            return 1
        if "insert into invoice_review_tasks" in text:
            task = {
                "id": len(self.tasks) + 1,
                "invoice_id": params[0],
                "review_result": params[3],
                "handler_user": params[4],
                "handling_note": params[5],
                "idempotency_key": params[7],
                "request_id": params[8],
            }
            self.tasks.append(task)
            return 1
        if "insert into invoice_state_transitions" in text:
            self.transitions.append({"from_status": params[1], "to_status": params[2], "idempotency_key": params[8]})
            return 1
        if "insert into invoice_events" in text:
            self.events.append({"invoice_id": params[0], "event_status": params[2], "payload": params[3]})
            return 1
        return 0


class OperationLockFakeDB:
    def __init__(self):
        self.locks: dict[str, dict] = {}
        self.now = dt.datetime(2026, 1, 1, 12, 0, 0)

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        params = params or ()
        if text.startswith("insert into app_operation_locks"):
            lock_name, owner, ttl = params
            existing = self.locks.get(lock_name)
            if not existing or existing["expires_at"] <= self.now:
                self.locks[lock_name] = {
                    "owner": owner,
                    "expires_at": self.now + dt.timedelta(seconds=int(ttl)),
                }
            return 1
        if text.startswith("delete from app_operation_locks"):
            lock_name, owner = params
            if self.locks.get(lock_name, {}).get("owner") == owner:
                del self.locks[lock_name]
                return 1
            return 0
        return 0

    def fetch_one(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        params = params or ()
        if "from app_operation_locks" in text:
            row = self.locks.get(params[0])
            return {"owner": row["owner"]} if row else None
        return None


class DashboardFakeDB:
    def fetch_one(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        if "sum(case when s.invoice_id is null" in text:
            return {"pending_count": 0, "failed_count": 0, "synced_count": 0}
        if "count(*) as total_count" in text:
            return {"total_count": 0, "risk_count": 0, "pending_count": 0, "today_count": 0}
        return {}

    def fetch_all(self, sql, params=None):
        return []


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.lastrowid = 1
        self.rowcount = 1

    def execute(self, sql, params=None):
        if self.connection.fail_next:
            self.connection.fail_next = False
            raise RuntimeError("boom")
        self.connection.executed.append(("execute", sql, params))
        return 1

    def executemany(self, sql, seq_params):
        self.connection.executed.append(("executemany", sql, tuple(seq_params)))
        self.rowcount = len(tuple(seq_params))
        return self.rowcount

    def fetchone(self):
        return {"ok": 1}

    def fetchall(self):
        return []

    def close(self):
        return None


class FakeConnection:
    def __init__(self):
        self.begin_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.fail_next = False
        self.executed: list[tuple] = []

    def cursor(self):
        return FakeCursor(self)

    def ping(self, reconnect=True):
        return None

    def begin(self):
        self.begin_count += 1

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        return None


class IngestionTransactionalFakeDB:
    def __init__(self):
        self.invoices: list[dict] = []
        self.items: list[dict] = []
        self.events: list[dict] = []
        self._draft: dict[str, list[dict]] | None = None
        self.begun = 0
        self.committed = 0
        self.rolled_back = 0

    def begin(self):
        self.begun += 1
        self._draft = {
            "invoices": [dict(item) for item in self.invoices],
            "items": [dict(item) for item in self.items],
            "events": [dict(item) for item in self.events],
        }

    def commit(self):
        self.committed += 1
        if self._draft is not None:
            self.invoices = self._draft["invoices"]
            self.items = self._draft["items"]
            self.events = self._draft["events"]
        self._draft = None

    def rollback(self):
        self.rolled_back += 1
        self._draft = None

    def _target(self, name: str) -> list[dict]:
        if self._draft is None:
            raise AssertionError("ingestion writes must happen inside an explicit transaction")
        return self._draft[name]


class FakeInvoiceRepo:
    def __init__(self, db: IngestionTransactionalFakeDB):
        self.db = db

    def find_by_unique_hash(self, unique_hash: str):
        rows = self.db._draft["invoices"] if self.db._draft is not None else self.db.invoices
        return next((row for row in rows if row.get("unique_hash") == unique_hash), None)

    def insert_invoice(self, row):
        target = self.db._target("invoices")
        invoice_id = len(target) + 1
        target.append({"id": invoice_id, **row})
        return invoice_id


class FakeItemRepo:
    def __init__(self, db: IngestionTransactionalFakeDB, *, fail=False):
        self.db = db
        self.fail = fail

    def insert_items(self, invoice_id, items):
        if self.fail:
            raise RuntimeError("item insert failed")
        target = self.db._target("items")
        for item in items:
            target.append({"invoice_id": invoice_id, **item})
        return len(items)


class FakeEventRepo:
    def __init__(self, db: IngestionTransactionalFakeDB, *, fail=False):
        self.db = db
        self.fail = fail

    def add_event(self, invoice_id, event_type, event_status, payload=None):
        if self.fail:
            raise RuntimeError("event insert failed")
        self.db._target("events").append(
            {
                "invoice_id": invoice_id,
                "event_type": event_type,
                "event_status": event_status,
                "payload": json.dumps(payload or {}, ensure_ascii=False),
            }
        )
        return 1


class PipelineStubService:
    def __init__(self, result):
        self._result = result
        self.invoice_repo = type("InvoiceRepoStub", (), {"db": None})()

    def ingest_invoice(self, **kwargs):
        return self._result


def actor(role: str = "reviewer") -> dict:
    return {"id": 7, "email": f"{role}@example.test", "role": role}


def test_review_submit_is_transactional_and_idempotent():
    db = ReviewFakeDB(status="Pending")
    result = update_invoice_review(
        db,
        invoice_id=1,
        purchase_order_no="PO-1",
        unique_hash="hash",
        handler_user="Riley",
        handler_reason="Approved after matching the purchase order evidence.",
        invoice_status="Approved",
        actor_user=actor("reviewer"),
        request_id="req-1",
        idempotency_key="review-key-1",
    )
    assert result.changed is True
    assert db.invoice_status == "Approved"
    assert db.tasks[0]["idempotency_key"] == "review-key-1"
    assert db.committed == 1

    duplicate = update_invoice_review(
        db,
        invoice_id=1,
        purchase_order_no="PO-1",
        unique_hash="hash",
        handler_user="Riley",
        handler_reason="A duplicate browser submit should not add another review task.",
        invoice_status="Rejected",
        actor_user=actor("reviewer"),
        request_id="req-2",
        idempotency_key="review-key-1",
    )
    assert duplicate.changed is False
    assert duplicate.invoice_status == "Approved"
    assert len(db.tasks) == 1
    assert db.committed == 2


def test_reviewer_cannot_reopen_terminal_status_but_admin_can():
    reviewer_db = ReviewFakeDB(status="Approved")
    with pytest.raises(InvalidStateTransition):
        update_invoice_review(
            reviewer_db,
            invoice_id=1,
            purchase_order_no="PO-1",
            unique_hash="hash",
            handler_user="Riley",
            handler_reason="Reviewer should not reopen a terminal decision.",
            invoice_status="Pending",
            actor_user=actor("reviewer"),
            request_id="req-3",
        )
    assert reviewer_db.rolled_back == 1

    admin_db = ReviewFakeDB(status="Approved")
    result = update_invoice_review(
        admin_db,
        invoice_id=1,
        purchase_order_no="PO-1",
        unique_hash="hash",
        handler_user="Admin",
        handler_reason="Admin reopens the case after a supplier correction.",
        invoice_status="Pending",
        actor_user=actor("admin"),
        request_id="req-4",
    )
    assert result.changed is True
    assert admin_db.invoice_status == "Pending"


def test_operation_lock_blocks_concurrent_retry_and_releases():
    db = OperationLockFakeDB()
    assert acquire_operation_lock(db, lock_name="feishu_retry", owner="run-a", ttl_sec=120) is True
    assert acquire_operation_lock(db, lock_name="feishu_retry", owner="run-b", ttl_sec=120) is False
    assert release_operation_lock(db, lock_name="feishu_retry", owner="run-a") == 1
    assert acquire_operation_lock(db, lock_name="feishu_retry", owner="run-b", ttl_sec=120) is True


def test_dashboard_summary_reads_connector_snapshot_without_live_checks(monkeypatch):
    def fail_live_check(*args, **kwargs):
        raise AssertionError("Dashboard summary must not run live connector checks.")

    monkeypatch.setattr(services, "integration_status", fail_live_check)
    services._CONNECTOR_CACHE["rows"] = []
    services._CONNECTOR_CACHE["expires_at"] = 0.0

    summary = services.build_dashboard_summary(DashboardFakeDB(), {})
    assert summary["connectors"]["total_count"] == len(services.CONNECTOR_NAMES)
    assert summary["connectors"]["blocked_count"] == len(services.CONNECTOR_NAMES)


def test_mysql_client_does_not_autocommit_inside_explicit_transaction(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setattr(mysql_mod.pymysql, "connect", lambda **kwargs: fake_conn)

    db = mysql_mod.MySQLClient(
        host="127.0.0.1",
        port=3307,
        user="invoice_app",
        password="secret",
        db="enterprise_ai",
        autocommit=False,
    )
    db.begin()
    db.execute("UPDATE invoices SET invoice_status=%s WHERE id=%s", ("Approved", 1))
    assert fake_conn.commit_count == 0
    db.commit()
    assert fake_conn.commit_count == 1


def test_ingestion_rolls_back_when_event_write_fails():
    db = IngestionTransactionalFakeDB()
    service = IngestionService(
        invoice_repo=FakeInvoiceRepo(db),
        item_repo=FakeItemRepo(db),
        event_repo=FakeEventRepo(db, fail=True),
    )

    result = service.ingest_invoice(
        raw_ocr_json={"text": "demo"},
        llm_json={
            "invoice_code": "INV-001",
            "invoice_number": "0001",
            "invoice_date": "2026-01-01",
            "seller_tax_id": "SELLER-TAX-ID",
            "total_amount_with_tax": "100.00",
            "invoice_items": [{"item_name": "Line 1", "item_amount": "100.00", "tax_rate": "13%", "tax_amount": "13.00"}],
        },
        source_file_path="invoices/demo.jpg",
        context={"purchase_order_no": "PO-1"},
    )

    assert result.ok is False
    assert result.action == "error"
    assert db.begun == 1
    assert db.committed == 0
    assert db.rolled_back == 1
    assert db.invoices == []
    assert db.items == []
    assert db.events == []


def test_pipeline_raises_when_required_risk_email_fails(monkeypatch, tmp_path):
    invoice_path = tmp_path / "invoice.jpg"
    invoice_path.write_bytes(b"demo")
    service = PipelineStubService(ingestion_mod.IngestResult(ok=True, action="inserted", invoice_id=7, unique_hash="hash-7"))

    monkeypatch.setattr(ingestion_mod, "_call_ocr", lambda file_path, cfg: {"text": "demo"})
    monkeypatch.setattr(ingestion_mod, "_extract_purchase_no", lambda cfg, file_path, ocr_text: "")
    monkeypatch.setattr(
        ingestion_mod,
        "_ocr_fallback_parse",
        lambda ocr_text, raw_ocr_json=None: {"risk": {"risk_flag": 1}, "invoice_items": []},
    )
    monkeypatch.setattr(
        ingestion_mod,
        "_send_risk_email_with_audit",
        lambda *args, **kwargs: type("AlertResult", (), {"sent": False, "error": "smtp down"})(),
    )

    with pytest.raises(RuntimeError) as exc_info:
        ingestion_mod.run_pipeline_for_invoice_image(
            str(invoice_path),
            {"EMAIL_ALERT_REQUIRED": True, "FEISHU_SYNC_MODE": "off"},
            service,
        )
    assert "Required risk email alert failed" in str(exc_info.value)


def test_pipeline_raises_when_required_feishu_sync_fails(monkeypatch, tmp_path):
    invoice_path = tmp_path / "invoice.jpg"
    invoice_path.write_bytes(b"demo")
    service = PipelineStubService(ingestion_mod.IngestResult(ok=True, action="inserted", invoice_id=8, unique_hash="hash-8"))

    monkeypatch.setattr(ingestion_mod, "_call_ocr", lambda file_path, cfg: {"text": "demo"})
    monkeypatch.setattr(ingestion_mod, "_extract_purchase_no", lambda cfg, file_path, ocr_text: "")
    monkeypatch.setattr(
        ingestion_mod,
        "_ocr_fallback_parse",
        lambda ocr_text, raw_ocr_json=None: {"risk": {"risk_flag": 0}, "invoice_items": []},
    )
    monkeypatch.setattr(ingestion_mod, "_send_risk_email_with_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(ingestion_mod, "_build_feishu_fields", lambda *args, **kwargs: {"invoice_id": "8"})
    monkeypatch.setattr(ingestion_mod, "_try_sync_to_feishu", lambda cfg, fields: (False, "feishu down"))
    monkeypatch.setattr(ingestion_mod, "_record_feishu_sync", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError) as exc_info:
        ingestion_mod.run_pipeline_for_invoice_image(
            str(invoice_path),
            {"FEISHU_SYNC_REQUIRED": True, "FEISHU_SYNC_MODE": "inline"},
            service,
        )
    assert "Required Feishu sync failed" in str(exc_info.value)
