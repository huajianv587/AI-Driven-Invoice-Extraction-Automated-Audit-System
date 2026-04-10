from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Tuple

from src.db.mysql_client import MySQLClient
from src.product.repositories import (
    EventRepository,
    ExtractionRepository,
    FileRepository,
    NotificationRepository,
    ProductInvoiceRepository,
    ReviewRepository,
    TaskRepository,
    UserRepository,
)
from src.product.schemas import (
    PROCESSING_STATUS_COMPLETED,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_NEEDS_REVIEW,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_REJECTED,
)
from src.product.security import can_access, new_session_token, session_expiry, verify_password
from src.product.settings import ProductSettings, get_settings
from src.services.dify_client import DifyClient
from src.services.email_delivery_checker import EmailDeliveryChecker
from src.services.ingestion_service import (
    _apply_risk_rules,
    _call_ocr,
    _extract_purchase_no,
    _fetch_purchase_order,
    _ocr_fallback_parse,
    flatten_outputs,
)
from src.services.risk_alert_service import RiskAlertService
from src.utils.hash_utils import build_invoice_unique_hash
from src.utils.logger import get_logger


logger = get_logger("invoice_audit.product")

CRITICAL_FIELDS = [
    "invoice_code",
    "invoice_number",
    "invoice_date",
    "seller_name",
    "total_amount_with_tax",
]


def create_db(settings: Optional[ProductSettings] = None) -> MySQLClient:
    config = settings or get_settings()
    return MySQLClient(**config.db_kwargs())


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _invoice_status_from_review(review_status: str) -> str:
    mapping = {
        REVIEW_STATUS_NEEDS_REVIEW: "NeedsReview",
        REVIEW_STATUS_APPROVED: "Approved",
        REVIEW_STATUS_REJECTED: "Rejected",
        REVIEW_STATUS_PENDING: "Pending",
    }
    return mapping.get(review_status, "Pending")


def _storage_extension(filename: str, mime_type: str) -> str:
    ext = Path(filename).suffix.strip()
    if ext:
        return ext.lower()
    guessed = mimetypes.guess_extension(mime_type or "")
    return guessed or ".bin"


def _copy_stream_to_path(stream: BinaryIO, target_path: Path) -> int:
    size = 0
    with target_path.open("wb") as out:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            size += len(chunk)
    return size


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class AuthenticatedUser:
    id: int
    username: str
    role: str


class LocalFileStorage:
    def __init__(self, settings: ProductSettings):
        self.settings = settings

    def save_upload(self, stream: BinaryIO, original_name: str, mime_type: str) -> Tuple[str, int, str]:
        stamp = datetime.utcnow().strftime("%Y%m%d")
        ext = _storage_extension(original_name, mime_type)
        target_dir = Path(self.settings.upload_dir) / stamp
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{uuid.uuid4().hex}{ext}"
        size_bytes = _copy_stream_to_path(stream, target_path)
        sha256 = _hash_file(target_path)
        return str(target_path), size_bytes, sha256

    def promote_processed(self, source_path: str) -> str:
        src = Path(source_path)
        target_dir = Path(self.settings.processed_dir) / datetime.utcnow().strftime("%Y%m%d")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / src.name
        if src.resolve() != target.resolve():
            shutil.copy2(src, target)
        return str(target)


class ProductApplication:
    def __init__(self, db: MySQLClient, settings: Optional[ProductSettings] = None):
        self.db = db
        self.settings = settings or get_settings()
        self.users = UserRepository(db)
        self.files = FileRepository(db)
        self.tasks = TaskRepository(db)
        self.invoices = ProductInvoiceRepository(db)
        self.extractions = ExtractionRepository(db)
        self.reviews = ReviewRepository(db)
        self.events = EventRepository(db)
        self.notifications = NotificationRepository(db)
        self.storage = LocalFileStorage(self.settings)

    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        user = self.users.find_by_username(username)
        if not user or not verify_password(password, user.get("password_hash") or ""):
            raise ValueError("Invalid username or password")
        token = new_session_token()
        expires_at = session_expiry(self.settings.auth_session_ttl_hours)
        self.users.create_session(int(user["id"]), token, expires_at.strftime("%Y-%m-%d %H:%M:%S"))
        return {
            "access_token": token,
            "expires_at": expires_at,
            "user": {"id": int(user["id"]), "username": user["username"], "role": user["role"]},
        }

    def get_session_user(self, token: str) -> AuthenticatedUser:
        row = self.users.find_session(token)
        if not row or int(row.get("is_active") or 0) != 1:
            raise ValueError("Session expired or invalid")
        self.users.touch_session(token)
        return AuthenticatedUser(id=int(row["user_id"]), username=row["username"], role=row["role"])

    def ensure_role(self, user: AuthenticatedUser, required_role: str) -> None:
        if not can_access(required_role, user.role):
            raise PermissionError(f"Role {user.role} cannot access {required_role} resources")

    def upload_invoice(self, *, file_stream: BinaryIO, filename: str, mime_type: str, actor: AuthenticatedUser) -> Dict[str, Any]:
        self.ensure_role(actor, "operator")
        storage_path, size_bytes, sha256 = self.storage.save_upload(file_stream, filename, mime_type)
        existing_file = self.files.find_by_sha256(sha256)
        if existing_file:
            try:
                os.remove(storage_path)
            except OSError:
                pass
            open_task = self.tasks.find_open_by_file_id(int(existing_file["id"]))
            if open_task:
                return open_task
            task = self.tasks.create(int(existing_file["id"]), actor.username)
            return task
        file_id = self.files.create(
            original_name=filename,
            storage_path=storage_path,
            mime_type=mime_type or "application/octet-stream",
            size_bytes=size_bytes,
            sha256=sha256,
            uploaded_by=actor.username,
        )
        return self.tasks.create(file_id, actor.username)

    def list_tasks(self, *, status: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        return self.tasks.list(status=status or None, limit=limit)

    def get_task(self, task_id: int) -> Dict[str, Any]:
        row = self.tasks.get(task_id)
        if not row:
            raise ValueError("Task not found")
        return row

    def retry_task(self, task_id: int, actor: AuthenticatedUser) -> Dict[str, Any]:
        self.ensure_role(actor, "operator")
        row = self.get_task(task_id)
        if row["retry_count"] >= self.settings.task_retry_limit:
            raise ValueError("Task exceeded retry limit")
        self.tasks.retry(task_id)
        return self.get_task(task_id)

    def list_invoices(self, *, q: str = "", review_status: str = "", processing_status: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        return self.invoices.list(q=q, review_status=review_status, processing_status=processing_status, limit=limit)

    def get_invoice_detail(self, invoice_id: int) -> Dict[str, Any]:
        detail = self.invoices.detail(invoice_id)
        if not detail["invoice"]:
            raise ValueError("Invoice not found")
        return detail

    def dashboard_summary(self) -> Dict[str, Any]:
        return self.invoices.summary()

    def submit_review(self, *, invoice_id: int, review_status: str, note: str, actor: AuthenticatedUser) -> Dict[str, Any]:
        self.ensure_role(actor, "reviewer")
        if review_status not in {REVIEW_STATUS_APPROVED, REVIEW_STATUS_REJECTED, REVIEW_STATUS_NEEDS_REVIEW}:
            raise ValueError("Unsupported review status")
        invoice = self.invoices.get(invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")
        with self.db.transaction():
            self.invoices.finalize_review(
                invoice_id,
                review_status=review_status,
                handler_user=actor.username,
                handler_reason=note,
            )
            self.reviews.create_action(
                invoice_id=invoice_id,
                action_type="MANUAL_REVIEW",
                review_status=review_status,
                actor_user_id=actor.id,
                actor_username=actor.username,
                note=note,
                payload={"previous_review_status": invoice.get("review_status")},
            )
            self.events.add(
                invoice_id=invoice_id,
                event_type="REVIEW_SUBMITTED",
                event_status=review_status,
                payload={"actor": actor.username, "note": note},
            )
        return self.get_invoice_detail(invoice_id)

    def process_task(self, task_id: int) -> Dict[str, Any]:
        task = self.get_task(task_id)
        file_row = self.files.get(int(task["invoice_file_id"]))
        if not file_row:
            self.tasks.mark_failed(task_id, "FILE_NOT_FOUND", f"File record missing for task {task_id}")
            raise ValueError("File record missing")

        started_at = time.time()
        source_path = str(file_row["storage_path"])
        cfg = self.settings.legacy_flat_config()

        raw_ocr_json = _call_ocr(source_path, cfg)
        ocr_text = (raw_ocr_json.get("extracted_text") or raw_ocr_json.get("text") or "").strip()

        outputs_schema_v1, provider, model_name, model_version, prompt_version, fallback_source = self._extract_schema(
            source_path=source_path,
            ocr_text=ocr_text,
        )
        purchase_no = _extract_purchase_no(cfg, source_path, ocr_text)
        context = self._build_context(purchase_no)
        outputs_schema_v1 = _apply_risk_rules(outputs_schema_v1, context)
        flat = flatten_outputs(outputs_schema_v1)
        confidence_by_field, confidence_overall = self._build_confidence(flat, fallback_source)
        review_status, review_reasons = self._decide_review(flat, confidence_overall, fallback_source)
        unique_hash = build_invoice_unique_hash(
            invoice_code=str(flat.get("invoice_code") or ""),
            invoice_number=str(flat.get("invoice_number") or ""),
            invoice_date=str(flat.get("invoice_date") or ""),
            seller_tax_id=str(flat.get("seller_tax_id") or ""),
            total_amount_with_tax=flat.get("total_amount_with_tax"),
        )

        expected_amount = context.get("expected_amount_with_tax")
        actual_amount = flat.get("total_amount_with_tax")
        amount_diff = None
        if expected_amount not in (None, "") and actual_amount not in (None, ""):
            try:
                amount_diff = float(actual_amount) - float(expected_amount)
            except Exception:
                amount_diff = None

        invoice_id = None
        extraction_id = None
        processed_path = self.storage.promote_processed(source_path)
        with self.db.transaction():
            existed = self.invoices.find_by_unique_hash(unique_hash)
            if existed:
                invoice_id = int(existed["id"])
                self.invoices.update_processing(
                    invoice_id,
                    processing_status=PROCESSING_STATUS_COMPLETED,
                    review_status=review_status,
                    current_task_id=task_id,
                    confidence_overall=confidence_overall,
                )
                self.events.add(
                    invoice_id=invoice_id,
                    event_type="DUPLICATE_DETECTED",
                    event_status=PROCESSING_STATUS_COMPLETED,
                    payload={"task_id": task_id, "unique_hash": unique_hash},
                )
            else:
                row = {
                    "invoice_type": flat.get("invoice_type"),
                    "invoice_code": flat.get("invoice_code"),
                    "invoice_number": flat.get("invoice_number"),
                    "invoice_date": flat.get("invoice_date"),
                    "check_code": flat.get("check_code"),
                    "machine_code": flat.get("machine_code"),
                    "invoice_status": _invoice_status_from_review(review_status),
                    "processing_status": PROCESSING_STATUS_COMPLETED,
                    "review_status": review_status,
                    "is_red_invoice": int(bool(flat.get("is_red_invoice"))),
                    "red_invoice_ref": flat.get("red_invoice_ref"),
                    "seller_name": flat.get("seller_name"),
                    "seller_tax_id": flat.get("seller_tax_id"),
                    "seller_address": flat.get("seller_address"),
                    "seller_phone": flat.get("seller_phone"),
                    "seller_bank": flat.get("seller_bank"),
                    "seller_bank_account": flat.get("seller_bank_account"),
                    "buyer_name": flat.get("buyer_name"),
                    "buyer_tax_id": flat.get("buyer_tax_id"),
                    "buyer_address": flat.get("buyer_address"),
                    "buyer_phone": flat.get("buyer_phone"),
                    "buyer_bank": flat.get("buyer_bank"),
                    "buyer_bank_account": flat.get("buyer_bank_account"),
                    "total_amount_without_tax": flat.get("total_amount_without_tax"),
                    "total_tax_amount": flat.get("total_tax_amount"),
                    "total_amount_with_tax": flat.get("total_amount_with_tax"),
                    "amount_in_words": flat.get("amount_in_words"),
                    "drawer": flat.get("drawer"),
                    "reviewer": flat.get("reviewer"),
                    "payee": flat.get("payee"),
                    "remarks": flat.get("remarks"),
                    "purchase_order_no": context.get("purchase_order_no"),
                    "source_file_path": processed_path,
                    "raw_ocr_json": raw_ocr_json,
                    "llm_json": outputs_schema_v1,
                    "schema_version": "v1",
                    "expected_amount": expected_amount,
                    "amount_diff": amount_diff,
                    "risk_flag": int((outputs_schema_v1.get("risk") or {}).get("risk_flag") or 0),
                    "risk_reason": (outputs_schema_v1.get("risk") or {}).get("risk_reason") or [],
                    "source_file_id": int(file_row["id"]),
                    "current_task_id": task_id,
                    "confidence_overall": confidence_overall,
                    "latest_extraction_id": None,
                    "unique_hash": unique_hash,
                }
                invoice_id = self.invoices.insert_invoice(row)
                self.invoices.insert_items(invoice_id, flat.get("invoice_items") or [])
                self.events.add(
                    invoice_id=invoice_id,
                    event_type="INGESTED",
                    event_status=PROCESSING_STATUS_COMPLETED,
                    payload={
                        "task_id": task_id,
                        "provider": provider,
                        "fallback_source": fallback_source,
                        "confidence_overall": confidence_overall,
                    },
                )

            extraction_id = self.extractions.create(
                invoice_id=invoice_id,
                task_id=task_id,
                provider=provider,
                model_name=model_name,
                model_version=model_version,
                prompt_version=prompt_version,
                fallback_source=fallback_source,
                confidence_overall=confidence_overall,
                confidence_by_field=confidence_by_field,
                raw_response={"raw_ocr_json": raw_ocr_json, "schema": outputs_schema_v1},
                normalized_schema=outputs_schema_v1,
            )
            self.db.execute(
                """
                UPDATE invoices
                SET latest_extraction_id=%s,
                    source_file_id=%s,
                    current_task_id=%s,
                    confidence_overall=%s,
                    review_status=%s,
                    invoice_status=%s,
                    processing_status='COMPLETED',
                    updated_at=UTC_TIMESTAMP()
                WHERE id=%s
                """,
                (
                    extraction_id,
                    int(file_row["id"]),
                    task_id,
                    confidence_overall,
                    review_status,
                    _invoice_status_from_review(review_status),
                    invoice_id,
                ),
            )
            self.tasks.mark_completed(task_id, invoice_id)
            self.reviews.create_action(
                invoice_id=invoice_id,
                action_type="SYSTEM_CLASSIFICATION",
                review_status=review_status,
                actor_user_id=0,
                actor_username="system",
                note=", ".join(review_reasons) or "Auto classified",
                payload={
                    "provider": provider,
                    "fallback_source": fallback_source,
                    "confidence_overall": confidence_overall,
                    "review_reasons": review_reasons,
                },
            )
            self.events.add(
                invoice_id=invoice_id,
                event_type="REVIEW_ROUTED",
                event_status=review_status,
                payload={"reasons": review_reasons, "confidence_overall": confidence_overall},
            )

        self._send_notification_if_needed(
            invoice_id=invoice_id,
            schema=outputs_schema_v1,
            context={
                **context,
                "invoice_id": invoice_id,
                "unique_hash": unique_hash,
                "invoice_file_name": os.path.basename(source_path),
                "amount_diff": amount_diff,
            },
        )
        logger.info(
            "processed task=%s invoice_id=%s provider=%s confidence=%.4f elapsed_ms=%s",
            task_id,
            invoice_id,
            provider,
            confidence_overall,
            int((time.time() - started_at) * 1000),
        )
        return self.get_invoice_detail(invoice_id)

    def _extract_schema(self, *, source_path: str, ocr_text: str) -> Tuple[Dict[str, Any], str, str, str, str, str]:
        settings = self.settings
        if settings.dify_api_key and settings.dify_workflow_id:
            try:
                dify = DifyClient(api_key=settings.dify_api_key, base_url=settings.dify_base_url)
                upload_id = dify.upload_file(source_path)
                file_input = DifyClient.build_file_input(upload_id, file_kind="image")
                inputs_primary = {settings.dify_image_key: file_input, "ocr_text": ocr_text}
                inputs_secondary = {settings.dify_image_key: [file_input], "ocr_text": ocr_text}
                dify_resp = None
                last_error = None
                for _ in range(settings.dify_retry_max):
                    try:
                        try:
                            dify_resp = dify.run_workflow(settings.dify_workflow_id, inputs_primary, timeout=180)
                        except Exception:
                            dify_resp = dify.run_workflow(settings.dify_workflow_id, inputs_secondary, timeout=180)
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc
                        time.sleep(settings.dify_retry_sleep_sec)
                if last_error is not None:
                    raise last_error
                outputs = (dify_resp.get("data") or {}).get("outputs") or {}
                if isinstance(outputs, dict) and outputs:
                    return outputs, "dify", "dify-workflow", settings.dify_workflow_id, "v1", "none"
            except Exception as exc:
                logger.warning("dify extraction failed, fallback to OCR regex: %s", repr(exc))
        return _ocr_fallback_parse(ocr_text), "ocr_fallback", "regex-fallback", "builtin", "v1", "ocr_regex"

    def _build_context(self, purchase_no: Optional[str]) -> Dict[str, Any]:
        if not purchase_no:
            return {"purchase_order_no": None}
        po = _fetch_purchase_order(self.db, purchase_no)
        if not po:
            return {"purchase_order_no": purchase_no}
        return {
            "purchase_order_no": po.get("purchase_no"),
            "expected_amount_with_tax": po.get("expected_amount") or po.get("total_amount_with_tax"),
            "supplier_name_expected": po.get("supplier") or po.get("supplier_name"),
            "purchaser_name": po.get("purchaser_name"),
            "purchase_order_date": po.get("purchase_order_date"),
            "purchaser_email": po.get("purchaser_email") or po.get("buyer_email"),
            "leader_email": po.get("leader_email"),
        }

    def _build_confidence(self, flat: Dict[str, Any], fallback_source: str) -> Tuple[Dict[str, float], float]:
        present_score = 0.92 if fallback_source == "none" else 0.55
        confidence_by_field: Dict[str, float] = {}
        for field in CRITICAL_FIELDS:
            confidence_by_field[field] = present_score if flat.get(field) not in (None, "", []) else 0.0
        invoice_items = flat.get("invoice_items") or []
        confidence_by_field["invoice_items"] = 0.85 if invoice_items else 0.2
        values = list(confidence_by_field.values())
        overall = round(sum(values) / len(values), 4) if values else 0.0
        return confidence_by_field, overall

    def _decide_review(self, flat: Dict[str, Any], confidence_overall: float, fallback_source: str) -> Tuple[str, List[str]]:
        reasons: List[str] = []
        risk = flat.get("risk_flag") or 0
        if int(risk) == 1:
            reasons.append("risk_flag")
        missing_critical = [field for field in CRITICAL_FIELDS if flat.get(field) in (None, "", [])]
        if missing_critical:
            reasons.append("missing:" + ",".join(missing_critical))
        if confidence_overall < self.settings.auto_review_confidence_threshold:
            reasons.append("low_confidence")
        if fallback_source != "none":
            reasons.append(f"fallback:{fallback_source}")
        if reasons:
            return REVIEW_STATUS_NEEDS_REVIEW, reasons
        return REVIEW_STATUS_APPROVED, ["auto_approved"]

    def _send_notification_if_needed(self, *, invoice_id: int, schema: Dict[str, Any], context: Dict[str, Any]) -> None:
        risk = schema.get("risk") or {}
        if int(risk.get("risk_flag") or 0) != 1:
            return
        if not self.settings.smtp_host:
            self.notifications.record(
                invoice_id=invoice_id,
                delivery_type="RISK_ALERT",
                channel="email",
                recipient=context.get("purchaser_email") or self.settings.alert_fallback_to,
                cc=[context.get("leader_email")] if context.get("leader_email") else [],
                status="SKIPPED",
                subject="[Invoice Risk Alert] SMTP not configured",
                payload={"reason": "smtp_not_configured"},
                error_message="SMTP host not configured",
            )
            return

        email_client = EmailDeliveryChecker(
            smtp_host=self.settings.smtp_host,
            smtp_port=self.settings.smtp_port,
            smtp_user=self.settings.smtp_user,
            smtp_pass=self.settings.smtp_pass,
            use_tls=self.settings.smtp_use_tls,
            use_ssl=self.settings.smtp_use_ssl,
            from_name=self.settings.smtp_from_name,
            from_email=self.settings.smtp_from_email,
        )
        alert = RiskAlertService(
            email_client=email_client,
            fallback_to=self.settings.alert_fallback_to,
            anomaly_form_base_url=self.settings.anomaly_form_base_url,
        )
        result = alert.send_alert_if_needed(schema, context)
        detail = result.detail or {}
        status = "SENT" if result.sent else ("FAILED" if result.error else "SKIPPED")
        self.notifications.record(
            invoice_id=invoice_id,
            delivery_type="RISK_ALERT",
            channel="email",
            recipient=detail.get("to") or context.get("purchaser_email") or self.settings.alert_fallback_to,
            cc=detail.get("cc") or [],
            status=status,
            subject=detail.get("subject") or "[Invoice Risk Alert]",
            payload=detail,
            error_message=result.error or "",
        )
        self.events.add(
            invoice_id=invoice_id,
            event_type="EMAIL_ALERT",
            event_status=status,
            payload={**detail, "error": result.error},
        )


def normalize_exception(exc: Exception) -> Tuple[str, str]:
    name = exc.__class__.__name__.upper()
    return name[:64], str(exc)[:4000]
