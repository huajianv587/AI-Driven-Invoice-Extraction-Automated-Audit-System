# src/services/ingestion_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import os
import json
import re
import traceback
import secrets
from datetime import datetime

from src.utils.logger import get_logger
from src.utils.hash_utils import build_invoice_unique_hash
from src.utils.flatten import build_feishu_fields_from_normalized
from src.risk.rules import apply_risk_rules
from src.utils.email_utils import send_alert_email
from src.config import get_app_base_url

from src.clients.ocr_client import OCRClient
from src.clients.dify_client import DifyClient
from src.db.repositories import (
    InvoiceRepository,
    InvoiceItemRepository,
    EventRepository,
    RiskRepository,
    PORepository,
)

logger = get_logger()

# -----------------------------
# Helpers
# -----------------------------
def _as_decimal_safe(x):
    if x is None:
        return None
    try:
        # 兼容 "1,234.50" 这种
        if isinstance(x, str):
            x = x.replace(",", "").strip()
        return float(x)
    except Exception:
        return None


INVOICE_COLS_ALLOWED = {
    "unique_hash",
    "source_file_path",
    "status",
    "invoice_code",
    "invoice_number",
    "invoice_date",
    "purchase_order_no",
    "seller_name",
    "buyer_name",
    "currency",
    "total_amount_with_tax",
    "tax_amount",
    "expected_amount",
    "amount_diff",
    "risk_flag",
    "risk_summary",
    "risk_reason",
    "raw_ocr_json",
    "llm_json",
    "normalized_json",
}


def filter_invoice_row_for_db(row: dict) -> dict:
    """只保留 invoices 表真实存在的列，避免 Unknown column"""
    return {k: row.get(k) for k in INVOICE_COLS_ALLOWED if k in row}


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)

def _extract_po_no(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"(PO|采购单号|订单号)\s*[:：]?\s*([A-Za-z0-9\-]{4,})", text, re.I)
    if m:
        return m.group(2)
    return None

def _get(d, path, default=None):
    """path like 'invoice_meta.invoice_code'"""
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur

def _find_invoice_by_unique_hash(invoice_repo, unique_hash: str):
    """
    兼容不同版本的 InvoiceRepository：
    - find_by_unique_hash / get_by_unique_hash / find_by_hash / get_by_hash
    - 如果都没有，就直接用 repo.db 查
    """
    for name in ("find_by_unique_hash", "get_by_unique_hash", "find_by_hash", "get_by_hash"):
        fn = getattr(invoice_repo, name, None)
        if callable(fn):
            return fn(unique_hash)

    # 最后兜底：直接查数据库
    db = getattr(invoice_repo, "db", None)
    if db is None:
        return None

    # 兼容你的 mysql_client 封装：db.fetch_one(sql, params)
    fetch_one = getattr(db, "fetch_one", None)
    if callable(fetch_one):
        return fetch_one(
            "SELECT id, unique_hash FROM invoices WHERE unique_hash=%s LIMIT 1",
            (unique_hash,)
        )

    return None

def _pick(d, *paths, default=None):
    for p in paths:
        v = _get(d, p, None)
        if v not in (None, "", [], {}):
            return v
    return default

def _normalize_llm_output(llm_json: Dict[str, Any], raw_ocr: Dict[str, Any]) -> Dict[str, Any]:
    """
    统一输出结构：invoice_meta/seller/buyer/totals/staff/invoice_items/risk
    注意：这里不往 invoice_meta 里强行塞 purchase_order_no（避免影响 unique_hash 的稳定性）
    """
    llm_json = llm_json or {}
    out = {
        "schema_version": llm_json.get("schema_version") or "v1",
        "invoice_meta": llm_json.get("invoice_meta") or {},
        "seller": llm_json.get("seller") or {},
        "buyer": llm_json.get("buyer") or {},
        "totals": llm_json.get("totals") or {},
        "staff": llm_json.get("staff") or {},
        "invoice_items": llm_json.get("invoice_items") or [],
        "risk": llm_json.get("risk") or {},
    }
    return out

def build_invoice_row_from_dify_v1(llm_json: dict) -> dict:
    """
    把 Dify v1 schema 映射成 invoices 表字段（你库里常用那些列）
    """
    meta = (llm_json or {}).get("invoice_meta") or {}
    seller = (llm_json or {}).get("seller") or {}
    buyer = (llm_json or {}).get("buyer") or {}
    totals = (llm_json or {}).get("totals") or {}
    staff = (llm_json or {}).get("staff") or {}
    risk = (llm_json or {}).get("risk") or {}

    row = {
        # ---- invoice main ----
        "invoice_type": meta.get("invoice_type"),
        "invoice_code": meta.get("invoice_code"),
        "invoice_number": meta.get("invoice_number"),
        "invoice_date": meta.get("invoice_date"),
        "check_code": meta.get("check_code"),
        "machine_code": meta.get("machine_code"),
        "is_red_invoice": meta.get("is_red_invoice", 0),
        "red_invoice_ref": meta.get("red_invoice_ref"),

        # ---- seller ----
        "seller_name": seller.get("seller_name"),
        "seller_tax_id": seller.get("seller_tax_id"),
        "seller_address": seller.get("seller_address"),
        "seller_phone": seller.get("seller_phone"),
        "seller_bank": seller.get("seller_bank"),
        "seller_bank_account": seller.get("seller_bank_account"),

        # ---- buyer ----
        "buyer_name": buyer.get("buyer_name"),
        "buyer_tax_id": buyer.get("buyer_tax_id"),
        "buyer_address": buyer.get("buyer_address"),
        "buyer_phone": buyer.get("buyer_phone"),
        "buyer_bank": buyer.get("buyer_bank"),
        "buyer_bank_account": buyer.get("buyer_bank_account"),

        # ---- totals ----
        "total_amount_without_tax": totals.get("total_amount_without_tax"),
        "total_tax_amount": totals.get("total_tax_amount"),
        "total_amount_with_tax": totals.get("total_amount_with_tax"),
        "amount_in_words": totals.get("amount_in_words"),

        # ---- staff ----
        "drawer": staff.get("drawer"),
        "reviewer": staff.get("reviewer"),
        "payee": staff.get("payee"),
        "remarks": staff.get("remarks"),

        # ---- risk ----
        "risk_flag": risk.get("risk_flag", 0),
        "risk_reason": risk.get("risk_reason") or [],  # ✅ 数组
    }

    # --- normalize invoice code/number to stabilize dedup ---
    row["invoice_code"] = re.sub(r"\D", "", str(row.get("invoice_code") or ""))
    row["invoice_number"] = re.sub(r"\D", "", str(row.get("invoice_number") or ""))

    return row


@dataclass
class IngestResult:
    ok: bool
    action: str  # inserted / skipped / error
    invoice_id: Optional[int] = None
    unique_hash: Optional[str] = None
    error: Optional[str] = None
    used_fallback: bool = False


def _try_sync_to_feishu(cfg: dict, invoice_id: int, normalized: dict, logger, event_repo=None) -> bool:
    """
    同步一条发票到飞书多维表（最佳努力：失败不影响主流程）
    关键修正：
    1) Upsert key 优先 unique_hash -> file_name -> (invoice_code+invoice_number)
    2) update 时不允许“垃圾文本”覆盖旧值（例如 buyer_name=纳税人识别号）
    3) Number 字段强制 float/None，避免 NumberFieldConvFail
    """
    import os

    def _to_str(v):
        if v is None:
            return ""
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    def _to_number(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if not s:
            return None
        s = s.replace(",", "")
        try:
            return float(s)
        except Exception:
            return None

    def _is_bad_text(s: str) -> bool:
        if not s:
            return True
        t = s.strip()
        bad_tokens = [
            "纳税人识别号", "识别号", "购买方", "销货方", "名称", "地址电话", "开户行及账号",
            "单位名称", "电话", "地址", "税号"
        ]
        if any(tok in t for tok in bad_tokens):
            return True
        if len(t) <= 2:
            return True
        return False

    # 0) cfg 读取（兼容大小写）
    app_id = cfg.get("FEISHU_APP_ID") or cfg.get("feishu_app_id") or ""
    app_secret = cfg.get("FEISHU_APP_SECRET") or cfg.get("feishu_app_secret") or ""
    app_token = cfg.get("FEISHU_APP_TOKEN") or cfg.get("feishu_app_token") or ""
    table_id = cfg.get("FEISHU_TABLE_ID") or cfg.get("feishu_table_id") or ""

    if not (app_id and app_secret and app_token and table_id):
        logger.warning("[FEISHU] missing cfg, skip.")
        return False

    # 1) client + token
    from src.clients.feishu_bitable_client import FeishuBitableClient
    client = FeishuBitableClient(app_id=app_id, app_secret=app_secret, app_token=app_token, table_id=table_id)

    token = client.get_tenant_token()
    if not token:
        logger.error("[FEISHU] get_tenant_token failed.")
        return False

    if not isinstance(normalized, dict):
        logger.error("[FEISHU] normalized is not dict. type=%s", type(normalized))
        return False

    invoice_meta = normalized.get("invoice_meta") or {}
    seller = normalized.get("seller") or {}
    buyer = normalized.get("buyer") or {}
    totals = normalized.get("totals") or {}

    unique_hash = _to_str(normalized.get("unique_hash")).strip()
    src_path = _to_str(normalized.get("source_file_path")).strip()
    file_name = os.path.basename(src_path) if src_path else ""

    invoice_code = _to_str(invoice_meta.get("invoice_code")).strip()
    invoice_number = _to_str(invoice_meta.get("invoice_number")).strip()

    buyer_name = _to_str(buyer.get("buyer_name")).strip()
    seller_name = _to_str(seller.get("seller_name")).strip()

    fields = {
        "invoice_id": _to_str(invoice_id),
        "file_name": _to_str(file_name),
        "source_file_path": _to_str(src_path),
        "unique_hash": _to_str(unique_hash),

        "invoice_code": _to_str(invoice_code),
        "invoice_number": _to_str(invoice_number),
        "invoice_date": _to_str(invoice_meta.get("invoice_date")),

        "seller_name": _to_str(seller_name),
        "buyer_name": _to_str("" if _is_bad_text(buyer_name) else buyer_name),

        "total_amount_with_tax": _to_number(totals.get("total_amount_with_tax")),
    }

    logger.info(
        "[FEISHU] upsert key: hash=%s file=%s code=%s number=%s total=%s",
        unique_hash, file_name, invoice_code, invoice_number, fields.get("total_amount_with_tax")
    )

    try:
        page_token = None
        target_record_id = None
        matched_old_fields = None

        for _ in range(20):
            resp_list = client.list_records(token, page_size=100, page_token=page_token)
            if not (isinstance(resp_list, dict) and resp_list.get("code") == 0):
                logger.error("[FEISHU] list_records failed: %s", resp_list)
                break

            data = resp_list.get("data") or {}
            items = data.get("items") or []

            for it in items:
                rid = it.get("record_id") or it.get("id")
                f = it.get("fields") or {}

                it_hash = _to_str(f.get("unique_hash")).strip()
                it_file = _to_str(f.get("file_name")).strip()
                it_code = _to_str(f.get("invoice_code")).strip()
                it_num = _to_str(f.get("invoice_number")).strip()

                hit = False
                if unique_hash and it_hash and it_hash == unique_hash:
                    hit = True
                elif file_name and it_file and it_file == file_name:
                    hit = True
                elif invoice_code and invoice_number and it_code == invoice_code and it_num == invoice_number:
                    hit = True

                if hit and rid:
                    target_record_id = rid
                    matched_old_fields = f
                    break

            if target_record_id:
                break

            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break

        # 防脏覆盖：新值明显垃圾，则保留旧值
        if target_record_id and isinstance(matched_old_fields, dict):
            old_buyer = _to_str(matched_old_fields.get("buyer_name")).strip()
            if _is_bad_text(fields.get("buyer_name", "")) and old_buyer:
                fields["buyer_name"] = old_buyer

            old_seller = _to_str(matched_old_fields.get("seller_name")).strip()
            if _is_bad_text(fields.get("seller_name", "")) and old_seller:
                fields["seller_name"] = old_seller

        if target_record_id:
            resp = client.update_record(token, target_record_id, fields)
            ok = isinstance(resp, dict) and resp.get("code") == 0
            if ok:
                logger.info("[FEISHU] update_record ok record_id=%s", target_record_id)
                return True
            logger.error("[FEISHU] update_record failed record_id=%s resp=%s", target_record_id, resp)
            return False

        resp = client.add_record(token, fields)
        ok = isinstance(resp, dict) and resp.get("code") == 0
        if ok:
            rid = ((resp.get("data") or {}).get("record") or {}).get("record_id")
            logger.info("[FEISHU] add_record ok record_id=%s", rid)
            return True

        logger.error("[FEISHU] add_record failed resp=%s", resp)
        return False

    except Exception as e:
        logger.exception("[FEISHU] sync exception: %s", e)
        return False

def _get_app_base_url_safe(cfg: dict) -> str:
    # 兼容你已有 get_app_base_url() 或者 env
    try:
        from src.config import get_app_base_url
        return get_app_base_url()
    except Exception:
        return cfg.get("APP_BASE_URL") or os.getenv("APP_BASE_URL") or "http://127.0.0.1:8000"


def _create_or_reuse_review_task_and_email(
    cfg: dict,
    db,                    # invoice_repo.db
    invoice_id: int,
    po_no: str,
    expected_amount: float,
    invoice_total: float,
    amount_diff: float,
    risk_summary: str,
    invoice_number: str,
    purchaser_email: str = None,
    leader_email: str = None,
    logger=None,
) -> int:
    """
    创建或复用一条 PENDING 的审批任务，并发送邮件（to采购员+cc领导）
    返回 task_id
    """
    from src.utils.email_utils import send_alert_email

    # 1) 先查有没有未完成 task，避免重复创建
    existed = db.fetch_one(
        "SELECT id, token, assigned_email, cc_email FROM approval_tasks "
        "WHERE invoice_id=%s AND status='PENDING' ORDER BY id DESC LIMIT 1",
        (invoice_id,)
    )

    if existed:
        task_id = int(existed["id"])
        token = existed.get("token") or ""
        purchaser_email = purchaser_email or existed.get("assigned_email")
        leader_email = leader_email or existed.get("cc_email")
    else:
        token = secrets.token_urlsafe(24)

        purchaser_email = purchaser_email or (cfg.get("DEFAULT_PURCHASER_EMAIL") or os.getenv("DEFAULT_PURCHASER_EMAIL"))
        leader_email = leader_email or (cfg.get("LEADER_EMAIL") or os.getenv("LEADER_EMAIL"))

        db.execute(
            "INSERT INTO approval_tasks(invoice_id,status,assigned_email,cc_email,token) "
            "VALUES(%s,'PENDING',%s,%s,%s)",
            (invoice_id, purchaser_email, leader_email, token),
        )
        row = db.fetch_one(
            "SELECT id, token, assigned_email, cc_email FROM approval_tasks "
            "WHERE invoice_id=%s ORDER BY id DESC LIMIT 1",
            (invoice_id,)
        )
        task_id = int(row["id"])
        token = row.get("token") or token
        purchaser_email = row.get("assigned_email") or purchaser_email
        leader_email = row.get("cc_email") or leader_email

    base = _get_app_base_url_safe(cfg)
    form_link = f"{base}/review/{task_id}?token={token}"
    inv_link = f"{base}/invoices/{invoice_id}"

    subject = f"[PO Amount Mismatch] Invoice {invoice_number or invoice_id} requires review"
    content = (
        f"检测到【采购订单金额】与【发票金额】不一致，请采购员核查并填写原因：\n\n"
        f"- invoice_id: {invoice_id}\n"
        f"- invoice_number: {invoice_number}\n"
        f"- PO No: {po_no}\n"
        f"- expected_amount: {expected_amount}\n"
        f"- invoice_total_with_tax: {invoice_total}\n"
        f"- amount_diff: {amount_diff}\n"
        f"- risk: {risk_summary}\n\n"
        f"👉 处理表单（填写原因/处理结果）：{form_link}\n"
        f"📄 发票详情：{inv_link}\n"
    )

    ok = send_alert_email(subject, content, to_email=purchaser_email, cc_email=leader_email)
    if logger:
        logger.info("[EMAIL] sent=%s to=%s cc=%s task_id=%s", ok, purchaser_email, leader_email, task_id)

    return task_id


# -----------------------------
# Main Pipeline
# -----------------------------
def run_pipeline_for_invoice_file(
    file_path: str,
    cfg: Dict[str, Any],
    invoice_repo: InvoiceRepository,
    item_repo: InvoiceItemRepository,
    event_repo: EventRepository,
    risk_repo: RiskRepository,
    po_repo: PORepository,
) -> IngestResult:
    action = "inserted"

    if not os.path.exists(file_path):
        return IngestResult(ok=False, action="error", error=f"File not found: {file_path}")

    # 1) OCR
    ocr = OCRClient(cfg.get("OCR_URL") or "", int(cfg.get("OCR_TIMEOUT_SEC") or 40))
    raw_ocr_json = ocr.extract(file_path)
    ocr_text = (raw_ocr_json or {}).get("text") or ""

    # 2) Dify
    dify_key = cfg.get("DIFY_API_KEY") or ""
    dify_base = cfg.get("DIFY_BASE_URL") or "https://api.dify.ai/v1"
    dify_image_key = cfg.get("DIFY_IMAGE_KEY") or "invoice"

    llm_json = None
    used_fallback = False

    if dify_key:
        try:
            dify = DifyClient(api_key=dify_key, base_url=dify_base)
            upload_id = dify.upload_file(file_path)

            ext = os.path.splitext(file_path.lower())[1]
            is_image = ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]

            file_obj = {
                "type": "image" if is_image else "document",
                "transfer_method": "local_file",
                "upload_file_id": upload_id,
            }

            inputs = {dify_image_key: file_obj}
            resp = dify.run_workflow(inputs=inputs)

            data = resp.get("data") or {}
            status = data.get("status")

            if status and status != "succeeded":
                raise RuntimeError(f"Dify workflow status={status}, error={data.get('error')}")

            logger.info("[DEBUG] dify resp keys: %s", list((resp or {}).keys()))
            logger.info("[DEBUG] dify resp head: %s", json.dumps(resp, ensure_ascii=False)[:1200])

            outputs = data.get("outputs") or {}

            def _try_parse_json_str(s: str):
                s = (s or "").strip()
                if not s:
                    return None
                try:
                    return json.loads(s)
                except Exception:
                    return None

            llm_json = None

            if isinstance(outputs, str):
                llm_json = _try_parse_json_str(outputs)

            elif isinstance(outputs, dict) and outputs:
                if "invoice_meta" in outputs and ("seller" in outputs or "buyer" in outputs or "totals" in outputs):
                    llm_json = outputs
                else:
                    for k in ("text", "result", "output", "output_text", "json"):
                        v = outputs.get(k)
                        if isinstance(v, str):
                            parsed = _try_parse_json_str(v)
                            if isinstance(parsed, dict):
                                llm_json = parsed
                                break

                    if llm_json is None and len(outputs) == 1:
                        only_v = next(iter(outputs.values()))
                        if isinstance(only_v, str):
                            parsed = _try_parse_json_str(only_v)
                            if isinstance(parsed, dict):
                                llm_json = parsed

            if llm_json is None:
                txt = (data.get("output_text") or "").strip()
                parsed = _try_parse_json_str(txt)
                if isinstance(parsed, dict):
                    llm_json = parsed

            def _is_empty_schema(d: dict) -> bool:
                if not isinstance(d, dict):
                    return True
                meta = d.get("invoice_meta") or {}
                seller = d.get("seller") or {}
                buyer = d.get("buyer") or {}
                totals = d.get("totals") or {}

                def _all_empty(x):
                    if not isinstance(x, dict):
                        return True
                    return all(v in (None, "", [], {}) for v in x.values()) if x else True

                return _all_empty(meta) and _all_empty(seller) and _all_empty(buyer) and _all_empty(totals)

            if llm_json is not None and _is_empty_schema(llm_json):
                logger.warning("[Dify] returned empty schema (all null). Treat as fallback.")
                llm_json = None
                used_fallback = True

        except Exception as e:
            used_fallback = True
            llm_json = None
            logger.warning("[Dify] failed -> fallback to OCR-only. err=%s\n%s", repr(e), traceback.format_exc())
    else:
        used_fallback = True

    # 3) fallback schema
    if llm_json is None:
        llm_json = {
            "schema_version": "v1",
            "invoice_meta": {
                "invoice_type": None,
                "invoice_code": None,
                "invoice_number": None,
                "invoice_date": None,
                "check_code": None,
                "machine_code": None,
                "is_red_invoice": 0,
                "red_invoice_ref": None,
            },
            "seller": {
                "seller_name": None,
                "seller_tax_id": None,
                "seller_address": None,
                "seller_phone": None,
                "seller_bank": None,
                "seller_bank_account": None,
            },
            "buyer": {
                "buyer_name": None,
                "buyer_tax_id": None,
                "buyer_address": None,
                "buyer_phone": None,
                "buyer_bank": None,
                "buyer_bank_account": None,
            },
            "invoice_items": [],
            "totals": {
                "total_amount_without_tax": None,
                "total_tax_amount": None,
                "total_amount_with_tax": None,
                "amount_in_words": None,
            },
            "staff": {"drawer": None, "reviewer": None, "payee": None, "remarks": None},
            "risk": {"risk_flag": 0, "risk_reason": ["OCR-only fallback"]},
        }

    normalized = _normalize_llm_output(llm_json, raw_ocr_json)

    # ✅✅✅ 关键：先把“文件来源信息”写进 normalized（但不要影响 unique_hash 的稳定性）
    normalized["source_file_path"] = file_path
    normalized["file_name"] = os.path.basename(file_path)

    # 4) unique_hash（用于幂等）
    unique_hash = build_invoice_unique_hash(normalized, raw_ocr_json=raw_ocr_json)

    # ✅✅✅ 关键：unique_hash 算出来之后，再写回 normalized（供 Feishu upsert 用）
    normalized["unique_hash"] = unique_hash

    existed = _find_invoice_by_unique_hash(invoice_repo, unique_hash)
    if existed:
        return IngestResult(
            ok=True,
            action="skipped",
            invoice_id=int(existed["id"]),
            unique_hash=unique_hash,
            used_fallback=used_fallback,
        )

    # 5) PO lookup
    po_no = _pick(normalized, "invoice_meta.purchase_order_no", default=None) or _extract_po_no(ocr_text)
    expected_amount = None
    if po_no:
        po = po_repo.get(str(po_no))
        if po:
            expected_amount = float(po["expected_amount"])

    # 6) Risk rules
    hits = apply_risk_rules(normalized, expected_amount=expected_amount)
    risk_flag = 1 if len(hits) > 0 else int(_pick(normalized, "risk.risk_flag", default=0))
    risk_summary = " | ".join([h.rule_id for h in hits]) if hits else None

    # 7) Prepare invoice row
    meta = normalized.get("invoice_meta") or {}
    seller = normalized.get("seller") or {}
    buyer = normalized.get("buyer") or {}
    totals = normalized.get("totals") or {}
    risk_obj = normalized.get("risk") or {}

    total_with_tax = _as_decimal_safe(totals.get("total_amount_with_tax"))
    tax_amt = _as_decimal_safe(totals.get("total_tax_amount"))

    row = {
        "unique_hash": unique_hash,
        "source_file_path": file_path,
        "status": "RISK_REVIEW" if risk_flag else "INGESTED",

        "invoice_code": meta.get("invoice_code"),
        "invoice_number": meta.get("invoice_number"),
        "invoice_date": meta.get("invoice_date"),
        "purchase_order_no": meta.get("purchase_order_no"),

        "seller_name": seller.get("seller_name"),
        "buyer_name": buyer.get("buyer_name"),

        "currency": totals.get("currency") if "currency" in totals else None,
        "total_amount_with_tax": total_with_tax,
        "tax_amount": tax_amt,
        "expected_amount": expected_amount,

        "amount_diff": (total_with_tax - expected_amount)
        if (expected_amount is not None and total_with_tax is not None)
        else None,

        "risk_flag": risk_flag,
        "risk_summary": risk_summary,
        "risk_reason": (risk_obj.get("risk_reason") or []),

        "raw_ocr_json": raw_ocr_json,
        "llm_json": llm_json,
        "normalized_json": normalized,
    }

    row = filter_invoice_row_for_db(row)

    # 8) Insert / idempotent by (invoice_code, invoice_number)
    invoice_code = (row.get("invoice_code") or "").strip()
    invoice_number = (row.get("invoice_number") or "").strip()

    existed = None
    if invoice_code and invoice_number:
        existed = invoice_repo.find_by_code_number(invoice_code, invoice_number)

    if existed:
        invoice_id = existed["id"]
        action = "updated"
        logger.info("Invoice exists (code+number). reuse invoice_id=%s", invoice_id)
    else:
        invoice_id = invoice_repo.insert_invoice(row)

    event_repo.add(invoice_id, "INGESTED", "invoice inserted", {"used_fallback": used_fallback})
    logger.info("[DEBUG] llm_json head: %s", json.dumps(llm_json, ensure_ascii=False)[:1500])

    # 9) Items
    items = normalized.get("invoice_items") or []
    item_repo.replace_items(invoice_id, items)

    # 10) Risk hits & approval task
    if risk_flag:
        for h in hits:
            risk_repo.add_hit(invoice_id, h.rule_id, h.severity, h.reason, h.evidence)
        event_repo.add(invoice_id, "RISK_HIT", f"{len(hits)} risk hits", {"hits": [h.__dict__ for h in hits]})

        # =========================
        # PO mismatch -> create/reuse review task + send email
        # =========================
        # 只对 PO 存在且 expected_amount 有值的情况触发采购核查
        THRESHOLD = float(cfg.get("PO_MISMATCH_THRESHOLD") or os.getenv("PO_MISMATCH_THRESHOLD") or 0.01)

        if po_no and expected_amount is not None and total_with_tax is not None:
            diff = (total_with_tax - expected_amount)
            if abs(diff) > THRESHOLD:
                # PO 表里如果有采购员/领导邮箱，优先用；否则 .env 兜底
                purchaser_email = None
                leader_email = None
                try:
                    po = po_repo.get(str(po_no))
                    if po:
                        purchaser_email = po.get("buyer_email") or po.get("purchaser_email")
                        leader_email = po.get("leader_email")
                except Exception:
                    pass

                task_id = _create_or_reuse_review_task_and_email(
                    cfg=cfg,
                    db=invoice_repo.db,
                    invoice_id=invoice_id,
                    po_no=str(po_no),
                    expected_amount=float(expected_amount),
                    invoice_total=float(total_with_tax),
                    amount_diff=float(diff),
                    risk_summary=risk_summary or "PO_AMOUNT_MISMATCH",
                    invoice_number=str(row.get("invoice_number") or ""),
                    purchaser_email=purchaser_email,
                    leader_email=leader_email,
                    logger=logger,
                )
                event_repo.add(
                    invoice_id,
                    "APPROVAL_CREATED",
                    "approval task created",
                    {"task_id": task_id, "po_no": str(po_no), "diff": float(diff), "threshold": THRESHOLD},
                )

    # 11) Feishu sync
    sync_mode = (cfg.get("FEISHU_SYNC_MODE") or "job").lower()

    if sync_mode == "off":
        logger.info("[FEISHU] sync_mode=off")
        try:
            event_repo.add(invoice_id, "FEISHU_SKIPPED_OFF", "sync_mode=off", None)
        except Exception:
            pass

    elif sync_mode == "inline":
        _try_sync_to_feishu(cfg, invoice_id, normalized, logger, event_repo)

    elif sync_mode == "job":
        logger.info("[FEISHU] job mode: enqueued via event_repo (not real async yet).")
        try:
            event_repo.add(invoice_id, "FEISHU_JOB_ENQUEUED", "job mode selected; no worker yet", None)
        except Exception:
            pass

    else:
        logger.info("[FEISHU] unknown sync_mode=%s, fallback inline", sync_mode)
        _try_sync_to_feishu(cfg, invoice_id, normalized, logger, event_repo)

    return IngestResult(
        ok=True,
        action=action,
        invoice_id=invoice_id,
        unique_hash=unique_hash,
        used_fallback=used_fallback,
    )



