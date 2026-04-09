# src/services/ingestion_service.py
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.utils.logger import get_logger
from src.utils.hash_utils import build_invoice_unique_hash
from src.db.repositories import InvoiceRepository, InvoiceItemRepository, InvoiceEventRepository
from src.services.dify_client import DifyClient

logger = get_logger()


# =========================
# Models
# =========================
@dataclass
class IngestResult:
    ok: bool
    action: str  # inserted / skipped / error
    invoice_id: Optional[int] = None
    unique_hash: Optional[str] = None
    error: Optional[str] = None


# =========================
# Small helpers
# =========================
def _cfg_pick(cfg: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for k in keys:
        v = cfg.get(k)
        if v is not None and str(v).strip() != "":
            return v
    return default


def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return None


def _to_decimal_2(x: Any) -> Optional[Decimal]:
    if x is None or x == "":
        return None
    try:
        return Decimal(str(x).replace(",", "").strip()).quantize(Decimal("0.01"))
    except Exception:
        return None


def _calc_amount_diff(expected_amount: Any, actual_amount: Any) -> Optional[float]:
    if expected_amount is None or actual_amount is None:
        return None
    try:
        expected = _to_decimal_2(expected_amount)
        actual = _to_decimal_2(actual_amount)
        if expected is None or actual is None:
            return None
        return float(actual - expected)
    except Exception:
        return None


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def flatten_outputs(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    把 Dify workflow 的 outputs（嵌套结构：invoice_meta/seller/buyer/totals/staff/risk/invoice_items）
    扁平化成 DB/Feishu 好用的一层字段。
    """
    if not isinstance(outputs, dict):
        return {}

    meta = outputs.get("invoice_meta") or {}
    seller = outputs.get("seller") or {}
    buyer = outputs.get("buyer") or {}
    totals = outputs.get("totals") or {}
    staff = outputs.get("staff") or {}
    risk = outputs.get("risk") or {}

    flat = {
        # meta
        "invoice_type": meta.get("invoice_type"),
        "invoice_code": meta.get("invoice_code"),
        "invoice_number": meta.get("invoice_number"),
        "invoice_date": meta.get("invoice_date"),
        "check_code": meta.get("check_code"),
        "machine_code": meta.get("machine_code"),
        "is_red_invoice": meta.get("is_red_invoice"),
        "red_invoice_ref": meta.get("red_invoice_ref"),

        # seller
        "seller_name": seller.get("seller_name"),
        "seller_tax_id": seller.get("seller_tax_id"),
        "seller_address": seller.get("seller_address"),
        "seller_phone": seller.get("seller_phone"),
        "seller_bank": seller.get("seller_bank"),
        "seller_bank_account": seller.get("seller_bank_account"),

        # buyer
        "buyer_name": buyer.get("buyer_name"),
        "buyer_tax_id": buyer.get("buyer_tax_id"),
        "buyer_address": buyer.get("buyer_address"),
        "buyer_phone": buyer.get("buyer_phone"),
        "buyer_bank": buyer.get("buyer_bank"),
        "buyer_bank_account": buyer.get("buyer_bank_account"),

        # totals
        "total_amount_without_tax": totals.get("total_amount_without_tax"),
        "total_tax_amount": totals.get("total_tax_amount"),
        "total_amount_with_tax": totals.get("total_amount_with_tax"),
        "amount_in_words": totals.get("amount_in_words"),

        # staff
        "drawer": staff.get("drawer"),
        "reviewer": staff.get("reviewer"),
        "payee": staff.get("payee"),
        "remarks": staff.get("remarks"),

        # risk
        "risk_flag": (risk.get("risk_flag") if isinstance(risk, dict) else 0),
        "risk_reason": (risk.get("risk_reason") if isinstance(risk, dict) else []),

        # items
        "invoice_items": outputs.get("invoice_items") or [],
    }
    return flat


def _extract_date_yyyy_mm_dd(text: str) -> Optional[str]:
    """
    支持：2017年12月01日 / 2024年01月12日 / 2024-01-12
    """
    text = text or ""
    m = re.search(r"(\d{4})[年\-\/\.](\d{1,2})[月\-\/\.](\d{1,2})日?", text)
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2))
    d = int(m.group(3))
    try:
        return f"{y:04d}-{mo:02d}-{d:02d}"
    except Exception:
        return None


def _ocr_fallback_parse(ocr_text: str) -> Dict[str, Any]:
    """
    Dify 失败时，从 OCR 文本兜底抠关键字段，避免 DB/飞书出现“第二行基本空”。
    """
    t = ocr_text or ""

    # 发票号码（No 00097000 / No05073978）
    invoice_number = None
    m = re.search(r"No\s*([0-9]{6,12})", t, flags=re.IGNORECASE)
    if m:
        invoice_number = m.group(1)

    # 发票代码（通常 10/12 位数字，OCR 文本里会多次出现；取最合理的一段）
    invoice_code = None
    codes = re.findall(r"\b(\d{10,12})\b", t)
    if codes:
        # 经验：发票代码一般是 10 位（增值税发票常见），也可能 12 位；取出现次数最多的
        from collections import Counter
        c = Counter(codes)
        invoice_code = c.most_common(1)[0][0]

    # 日期
    invoice_date = _extract_date_yyyy_mm_dd(t)

    # 价税合计（小写）通常有 ¥1044333.98 或 ￥110657.00
    total_with_tax = None
    # 优先找（小写）附近金额
    m = re.search(r"（小写）\s*[¥￥]\s*([0-9\.,]+)", t)
    if m:
        total_with_tax = _to_float(m.group(1))
    if total_with_tax is None:
        # 退一步：找 “￥110657.00” 这种最后的大金额（取最大的一个）
        nums = re.findall(r"[¥￥]\s*([0-9\.,]+)", t)
        if nums:
            vals = []
            for s in nums:
                v = _to_float(s)
                if v is not None:
                    vals.append(v)
            if vals:
                total_with_tax = max(vals)

    # 不含税/税额（如果 OCR 里出现 “￥94578.64” “¥16078.36”）
    # 这里不强求，能抠就抠；抠不到也没关系
    total_without_tax = None
    total_tax = None
    # 常见：先出现不含税合计，再出现税额合计
    m1 = re.search(r"合\s*计\s*[¥￥]\s*([0-9\.,]+)", t)
    if m1:
        total_without_tax = _to_float(m1.group(1))
    # 税额合计常见紧随其后第二个金额
    all_money = re.findall(r"[¥￥]\s*([0-9\.,]+)", t)
    if len(all_money) >= 2 and total_without_tax is not None:
        # 粗略：取第二个当税额（不保证 100%）
        cand_tax = _to_float(all_money[1])
        if cand_tax is not None:
            total_tax = cand_tax

    # 发票类型（含 “增值税专用发票”）
    invoice_type = None
    if "增值税专用发票" in t:
        invoice_type = "增值税专用发票"
    elif "普通发票" in t:
        invoice_type = "普通发票"

    schema = {
        "invoice_meta": {
            "invoice_type": invoice_type,
            "invoice_code": invoice_code,
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "check_code": "",
            "machine_code": "",
            "is_red_invoice": False,
            "red_invoice_ref": "",
        },
        "seller": {},
        "buyer": {},
        "totals": {
            "total_amount_without_tax": total_without_tax,
            "total_tax_amount": total_tax,
            "total_amount_with_tax": total_with_tax,
            "amount_in_words": "",
        },
        "staff": {},
        "risk": {"risk_flag": 0, "risk_reason": []},
        "invoice_items": [],
        "_fallback": {"source": "ocr_regex"},
    }
    return schema


def _extract_purchase_no(cfg: Dict[str, Any], source_file_path: str, ocr_text: str) -> Optional[str]:
    """
    让你不改 Dify 也能跑 PO 对账：
    优先级：
    1) cfg 显式给 purchase_no / PO_NO
    2) OCR 文本里找 “采购单号/PO:xxxxx”
    3) 文件名里：PO-XXXX__invoice.jpg 或 PO-XXXX_invoice.jpg 取 PO-XXXX
    """
    v = _cfg_pick(cfg, ["purchase_no", "PO_NO", "PURCHASE_NO"])
    if v:
        return _safe_str(v)

    t = ocr_text or ""
    m = re.search(r"(采购单号|PO|P\.O\.)\s*[:：]?\s*([A-Za-z0-9\-]{4,64})", t, flags=re.IGNORECASE)
    if m:
        return _safe_str(m.group(2))

    base = os.path.basename(source_file_path)
    name, _ = os.path.splitext(base)

    # 支持：PO-TEST-0001__invoice / PO-TEST-0001_invoice
    m = re.match(r"^(PO[\-_]?[A-Za-z0-9\-]{3,64})[__\-_].*$", name, flags=re.IGNORECASE)
    if m:
        return _safe_str(m.group(1))

    return None


# =========================
# OCR call
# =========================
def _call_ocr(file_path: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    你当前 OCR 服务：OCR_BASE_URL 默认 http://127.0.0.1:8000
    假设接口：POST /ocr  form-data(file)
    如果你接口不同，改这里即可。
    """
    base = _cfg_pick(cfg, ["ocr_base_url", "OCR_BASE_URL"], "http://127.0.0.1:8000")
    url = base.rstrip("/") + "/ocr"
    max_retry = int(_cfg_pick(cfg, ["OCR_RETRY_MAX"], 5) or 5)
    sleep_sec = float(_cfg_pick(cfg, ["OCR_RETRY_SLEEP_SEC"], 2.0) or 2.0)
    last_err = None

    for attempt in range(1, max_retry + 1):
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                resp = requests.post(url, files=files, timeout=60)

            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                return {"status": "error", "text": str(data)}
            return data
        except Exception as exc:
            last_err = exc
            if attempt >= max_retry:
                break
            logger.warning("[WARN] OCR request failed (attempt %s/%s): %s", attempt, max_retry, repr(exc))
            time.sleep(sleep_sec)

    raise last_err


# =========================
# Purchase Order fetch (simple)
# =========================
def _fetch_purchase_order(db, purchase_no: str) -> Optional[Dict[str, Any]]:
    """
    默认表名 purchase_orders（你如果实际表名不同，把这里改掉）。
    db 是你 main.py 里的 DB 适配器（有 fetch_one）。
    """
    if not purchase_no:
        return None
    try:
        return db.fetch_one(
            "SELECT * FROM purchase_orders WHERE purchase_no=%s LIMIT 1",
            (purchase_no,),
        )
    except Exception as e:
        logger.warning(f"[PO] fetch failed (ignored): {repr(e)}")
        return None


# =========================
# Risk Rules (use your module if exists)
# =========================
def _apply_risk_rules(invoice_schema_v1: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    直接复用你给的 RiskRules（如果文件已存在）。
    """
    try:
        from src.services.risk_rules import RiskRules
        rr = RiskRules()
        return rr.merge_into_invoice(invoice_schema_v1, context)
    except Exception as e:
        logger.warning(f"[RISK] risk_rules import/apply failed (ignored): {repr(e)}")
        # 保底：不影响主流程
        invoice_schema_v1.setdefault("risk", {"risk_flag": 0, "risk_reason": []})
        return invoice_schema_v1


# =========================
# Email alert (use your module if exists)
# =========================
def _send_risk_email_if_needed(invoice_schema_v1: Dict[str, Any], context: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    """
    使用你给的 EmailDeliveryChecker + RiskAlertService
    - 收件人：PO 里的 purchaser_email
    - 抄送：PO 里的 leader_email
    """
    try:
        from src.services.email_delivery_checker import EmailDeliveryChecker
        from src.services.risk_alert_service import RiskAlertService

        smtp_host = _cfg_pick(cfg, ["SMTP_HOST"], "")
        smtp_port = int(_cfg_pick(cfg, ["SMTP_PORT"], 587) or 587)
        smtp_user = _cfg_pick(cfg, ["SMTP_USER"], "")
        smtp_pass = _cfg_pick(cfg, ["SMTP_PASS"], "")

        if not (smtp_host and smtp_user and smtp_pass):
            logger.warning("[EMAIL] SMTP not configured. Skip sending email.")
            return

        # 兼容布尔值字符串配置
        use_tls = str(_cfg_pick(cfg, ["SMTP_USE_TLS"], "1")).strip().lower() not in ("0", "false", "no")
        use_ssl = str(_cfg_pick(cfg, ["SMTP_USE_SSL"], "0")).strip().lower() in ("1", "true", "yes")

        form_base = _cfg_pick(cfg, ["ANOMALY_FORM_BASE_URL"], None)

        # ✅ [优化] 获取 from_email 配置
        from_email = _cfg_pick(cfg, ["SMTP_FROM_EMAIL", "MAIL_FROM_EMAIL"], smtp_user)

        email_client = EmailDeliveryChecker(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_pass=smtp_pass,
            use_tls=use_tls,
            use_ssl=use_ssl,
            timeout_sec=20,
            from_name=_cfg_pick(cfg, ["SMTP_FROM_NAME"], "AI 财务审计系统"),
            from_email=from_email,  # ✅ [新增] 传入 from_email
        )

        alert = RiskAlertService(
            email_client=email_client,
            fallback_to=_cfg_pick(cfg, ["ALERT_FALLBACK_TO"], smtp_user),
            anomaly_form_base_url=form_base,
        )

        # 关键：抄送上级
        purchaser_email = _safe_str(context.get("purchaser_email"))
        leader_email = _safe_str(context.get("leader_email"))
        if purchaser_email:
            context["purchaser_email"] = purchaser_email
        if leader_email:
            context["leader_email"] = leader_email

        # 这里复用你的 RiskAlertService，但它当前 send_text_email 没传 cc
        # 所以我们在这里直接调用 EmailDeliveryChecker 发邮件（更稳）
        risk = invoice_schema_v1.get("risk") or {}
        if int(risk.get("risk_flag") or 0) != 1:
            return

        subject = alert._build_subject(invoice_schema_v1, context)
        content = alert._build_content(invoice_schema_v1, context)

        to_email = purchaser_email or _cfg_pick(cfg, ["ALERT_FALLBACK_TO"], smtp_user)
        cc_list = [leader_email] if leader_email else []

        res = email_client.send_text_email(
            to_email=to_email,
            subject=subject,
            content=content,
            cc=cc_list,
        )
        if res.ok:
            logger.info(f"[EMAIL] sent to={to_email} cc={cc_list}")
        else:
            logger.warning(f"[EMAIL] send failed: {res.error}")

    except Exception as e:
        logger.warning(f"[EMAIL] send_risk_email_if_needed failed (ignored): {repr(e)}")


# =========================
# Feishu sync (optional)
# =========================
def _try_sync_to_feishu(cfg: Dict[str, Any], fields: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    同步到飞书多维表格：
    - 字段名必须与多维表列名完全一致
    - 这里做“值类型兜底”，尽量不因为类型问题失败
    """
    app_id = _cfg_pick(cfg, ["feishu_app_id", "FEISHU_APP_ID"])
    app_secret = _cfg_pick(cfg, ["feishu_app_secret", "FEISHU_APP_SECRET"])
    app_token = _cfg_pick(cfg, ["feishu_app_token", "FEISHU_APP_TOKEN", "bitable_app_token"])
    table_id = _cfg_pick(cfg, ["feishu_table_id", "FEISHU_TABLE_ID", "bitable_table_id"])

    if not (app_id and app_secret and app_token and table_id):
        return False, "feishu config missing"

    try:
        from src.services.feishu_bitable_client import FeishuBitableClient

        client = FeishuBitableClient(app_id=app_id, app_secret=app_secret, app_token=app_token, table_id=table_id)
        token = client.get_tenant_token()
        if not token:
            return False, "tenant_token empty"

        # 类型兜底：dict/list -> json string；invoice_id 等强制字符串
        safe_fields: Dict[str, Any] = {}
        force_str_keys = {
            "invoice_id", "unique_hash", "ingest_action", "invoice_code", "invoice_number",
            "invoice_date", "seller_tax_id", "buyer_tax_id", "source_file_path", "file_name",
            "risk_reason",
        }
        for k, v in (fields or {}).items():
            if v is None:
                safe_fields[k] = ""
                continue
            if k in force_str_keys:
                if isinstance(v, (dict, list)):
                    safe_fields[k] = json.dumps(v, ensure_ascii=False)
                else:
                    safe_fields[k] = str(v)
                continue
            if isinstance(v, (dict, list)):
                safe_fields[k] = json.dumps(v, ensure_ascii=False)
                continue
            safe_fields[k] = v

        ok, msg = client.add_record(token, safe_fields)
        return ok, msg
    except Exception as e:
        return False, repr(e)


def _build_feishu_fields(
    invoice_schema_v1: Dict[str, Any],
    context: Dict[str, Any],
    result: IngestResult,
    source_file_path: str,
) -> Dict[str, Any]:
    flat = flatten_outputs(invoice_schema_v1 or {})
    expected_amount = context.get("expected_amount_with_tax")
    amount_diff = _calc_amount_diff(expected_amount, flat.get("total_amount_with_tax"))

    return {
        "invoice_id": result.invoice_id,
        "unique_hash": result.unique_hash,
        "ingest_action": result.action,
        "file_name": os.path.basename(source_file_path),
        "source_file_path": source_file_path,
        "purchase_order_no": context.get("purchase_order_no"),
        "invoice_code": flat.get("invoice_code"),
        "invoice_number": flat.get("invoice_number"),
        "invoice_date": flat.get("invoice_date"),
        "invoice_type": flat.get("invoice_type"),
        "seller_name": flat.get("seller_name"),
        "seller_tax_id": flat.get("seller_tax_id"),
        "buyer_name": flat.get("buyer_name"),
        "buyer_tax_id": flat.get("buyer_tax_id"),
        "total_amount_without_tax": flat.get("total_amount_without_tax"),
        "total_tax_amount": flat.get("total_tax_amount"),
        "total_amount_with_tax": flat.get("total_amount_with_tax"),
        "expected_amount": expected_amount,
        "amount_diff": amount_diff,
        "risk_flag": flat.get("risk_flag", 0),
        "risk_reason": flat.get("risk_reason", []),
    }


def _record_feishu_sync(db, invoice_id: Optional[int], response: Any = None, error: Optional[str] = None) -> None:
    if not invoice_id or db is None:
        return

    if error:
        db.execute(
            """
            INSERT INTO invoice_feishu_sync(invoice_id, feishu_record_id, synced_at, sync_error)
            VALUES(%s, NULL, NULL, %s)
            ON DUPLICATE KEY UPDATE sync_error=VALUES(sync_error), updated_at=NOW()
            """,
            (invoice_id, str(error)[:2000]),
        )
        return

    record_id = None
    if isinstance(response, dict):
        record_id = ((response.get("data") or {}).get("record") or {}).get("record_id")

    db.execute(
        """
        INSERT INTO invoice_feishu_sync(invoice_id, feishu_record_id, synced_at, sync_error)
        VALUES(%s, %s, NOW(), NULL)
        ON DUPLICATE KEY UPDATE
          feishu_record_id=VALUES(feishu_record_id),
          synced_at=VALUES(synced_at),
          sync_error=NULL,
          updated_at=NOW()
        """,
        (invoice_id, record_id),
    )


def _send_risk_email_with_audit(
    invoice_schema_v1: Dict[str, Any],
    context: Dict[str, Any],
    cfg: Dict[str, Any],
    db: Any = None,
    invoice_id: Optional[int] = None,
):
    try:
        from src.services.email_delivery_checker import EmailDeliveryChecker
        from src.services.risk_alert_service import AlertResult, RiskAlertService

        risk = invoice_schema_v1.get("risk") or {}
        if int(risk.get("risk_flag") or 0) != 1:
            result = AlertResult(ok=True, sent=False, detail={"message": "no risk"})
        else:
            smtp_host = _cfg_pick(cfg, ["SMTP_HOST"], "")
            if not smtp_host:
                result = AlertResult(ok=False, sent=False, error="SMTP host not configured")
            else:
                email_client = EmailDeliveryChecker(
                    smtp_host=smtp_host,
                    smtp_port=int(_cfg_pick(cfg, ["SMTP_PORT"], 1025) or 1025),
                    smtp_user=_cfg_pick(cfg, ["SMTP_USER"], ""),
                    smtp_pass=_cfg_pick(cfg, ["SMTP_PASS"], ""),
                    use_tls=str(_cfg_pick(cfg, ["SMTP_USE_TLS"], "0")).strip().lower() in ("1", "true", "yes"),
                    use_ssl=str(_cfg_pick(cfg, ["SMTP_USE_SSL"], "0")).strip().lower() in ("1", "true", "yes"),
                    timeout_sec=20,
                    from_name=_cfg_pick(cfg, ["SMTP_FROM_NAME"], "AI Invoice Audit System"),
                    from_email=_cfg_pick(
                        cfg,
                        ["SMTP_FROM_EMAIL", "MAIL_FROM_EMAIL", "SMTP_USER"],
                        "noreply@invoice-audit.local",
                    ),
                )
                alert = RiskAlertService(
                    email_client=email_client,
                    fallback_to=_cfg_pick(
                        cfg,
                        ["ALERT_FALLBACK_TO", "SMTP_USER"],
                        "finance-demo@local.test",
                    ),
                    anomaly_form_base_url=_cfg_pick(cfg, ["ANOMALY_FORM_BASE_URL"], None),
                )
                result = alert.send_alert_if_needed(invoice_schema_v1, context)
    except Exception as exc:
        logger.warning("[EMAIL] audited send failed (ignored): %s", repr(exc))
        result = None

    if db is not None and invoice_id:
        detail = getattr(result, "detail", None) or {}
        to_email = _safe_str(detail.get("to"))
        cc_list = detail.get("cc") if isinstance(detail.get("cc"), list) else []

        if getattr(result, "sent", False):
            status = "Sent"
            event_status = "SENT"
        elif getattr(result, "error", None):
            status = "Failed"
            event_status = "FAILED"
        else:
            status = "Skipped"
            event_status = "SKIPPED"

        db.execute(
            """
            UPDATE invoices
            SET notify_personal_status=%s,
                notify_leader_status=%s,
                updated_at=NOW()
            WHERE id=%s
            """,
            (
                status if to_email else "NotSent",
                status if cc_list else "NotSent",
                invoice_id,
            ),
        )
        payload = {
            "status": status,
            "to": to_email,
            "cc": cc_list,
            "subject": detail.get("subject"),
            "form_link": detail.get("form_link"),
            "error": getattr(result, "error", None),
        }
        db.execute(
            """
            INSERT INTO invoice_events(invoice_id, event_type, event_status, payload)
            VALUES(%s, %s, %s, %s)
            """,
            (invoice_id, "EMAIL_ALERT", event_status, json.dumps(payload, ensure_ascii=False)),
        )

    return result


# =========================
# Core Service
# =========================
class IngestionService:
    def __init__(
        self,
        invoice_repo: InvoiceRepository,
        item_repo: Optional[InvoiceItemRepository] = None,
        event_repo: Optional[InvoiceEventRepository] = None,
    ):
        self.invoice_repo = invoice_repo
        self.item_repo = item_repo
        self.event_repo = event_repo

    def ingest_invoice(
        self,
        raw_ocr_json: Dict[str, Any],
        llm_json: Optional[Dict[str, Any]],
        source_file_path: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> IngestResult:
        """
        幂等入库：
        - 生成 unique_hash
        - 已存在 => skipped
        - 不存在 => insert invoices + insert invoice_items(可选)
        """
        context = context or {}

        # 统一得到 schema_v1 & flat
        if llm_json and ("invoice_meta" in llm_json or "seller" in llm_json or "totals" in llm_json):
            schema_v1 = llm_json
            flat = flatten_outputs(schema_v1)
        else:
            schema_v1 = {}
            flat = llm_json or {}

        # 若 schema_v1 为空，但 flat 有 meta 字段，也补一个（兼容你以前的写法）
        if not schema_v1:
            schema_v1 = {
                "invoice_meta": {
                    "invoice_type": flat.get("invoice_type"),
                    "invoice_code": flat.get("invoice_code"),
                    "invoice_number": flat.get("invoice_number"),
                    "invoice_date": flat.get("invoice_date"),
                    "check_code": flat.get("check_code"),
                    "machine_code": flat.get("machine_code"),
                    "is_red_invoice": flat.get("is_red_invoice"),
                    "red_invoice_ref": flat.get("red_invoice_ref"),
                },
                "seller": {
                    "seller_name": flat.get("seller_name"),
                    "seller_tax_id": flat.get("seller_tax_id"),
                    "seller_address": flat.get("seller_address"),
                    "seller_phone": flat.get("seller_phone"),
                    "seller_bank": flat.get("seller_bank"),
                    "seller_bank_account": flat.get("seller_bank_account"),
                },
                "buyer": {
                    "buyer_name": flat.get("buyer_name"),
                    "buyer_tax_id": flat.get("buyer_tax_id"),
                    "buyer_address": flat.get("buyer_address"),
                    "buyer_phone": flat.get("buyer_phone"),
                    "buyer_bank": flat.get("buyer_bank"),
                    "buyer_bank_account": flat.get("buyer_bank_account"),
                },
                "totals": {
                    "total_amount_without_tax": flat.get("total_amount_without_tax"),
                    "total_tax_amount": flat.get("total_tax_amount"),
                    "total_amount_with_tax": flat.get("total_amount_with_tax"),
                    "amount_in_words": flat.get("amount_in_words"),
                },
                "staff": {
                    "drawer": flat.get("drawer"),
                    "reviewer": flat.get("reviewer"),
                    "payee": flat.get("payee"),
                    "remarks": flat.get("remarks"),
                },
                "risk": {
                    "risk_flag": flat.get("risk_flag", 0),
                    "risk_reason": flat.get("risk_reason", []),
                },
                "invoice_items": flat.get("invoice_items") or [],
            }
            flat = flatten_outputs(schema_v1)

        # unique_hash（企业级去重）
        unique_hash = build_invoice_unique_hash(
            invoice_code=_safe_str(flat.get("invoice_code")),
            invoice_number=_safe_str(flat.get("invoice_number")),
            invoice_date=_safe_str(flat.get("invoice_date")),
            seller_tax_id=_safe_str(flat.get("seller_tax_id")),
            total_amount_with_tax=flat.get("total_amount_with_tax"),
        )

        # 已存在？
        existed = self.invoice_repo.find_by_unique_hash(unique_hash)
        if existed:
            return IngestResult(ok=True, action="skipped", invoice_id=int(existed.get("id")), unique_hash=unique_hash)

        # 业务上下文：expected / supplier / emails
        expected_amount = context.get("expected_amount_with_tax")
        actual_amount = flat.get("total_amount_with_tax")
        amount_diff = _calc_amount_diff(expected_amount, actual_amount)

        # 风险计算写回 schema_v1（并把 risk 写进 flat）
        schema_v1 = _apply_risk_rules(schema_v1, context)
        flat = flatten_outputs(schema_v1)

        # 组装 invoices row
        row = {
            # meta
            "invoice_type": flat.get("invoice_type"),
            "invoice_code": flat.get("invoice_code"),
            "invoice_number": flat.get("invoice_number"),
            "invoice_date": flat.get("invoice_date"),
            "check_code": flat.get("check_code"),
            "machine_code": flat.get("machine_code"),
            "invoice_status": "Pending",
            "is_red_invoice": int(bool(flat.get("is_red_invoice"))),
            "red_invoice_ref": flat.get("red_invoice_ref"),

            # seller/buyer
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

            # totals
            "total_amount_without_tax": flat.get("total_amount_without_tax"),
            "total_tax_amount": flat.get("total_tax_amount"),
            "total_amount_with_tax": flat.get("total_amount_with_tax"),
            "amount_in_words": flat.get("amount_in_words"),

            # staff
            "drawer": flat.get("drawer"),
            "reviewer": flat.get("reviewer"),
            "payee": flat.get("payee"),
            "remarks": flat.get("remarks"),
            "purchase_order_no": context.get("purchase_order_no"),

            # audit/meta
            "source_file_path": source_file_path,
            "raw_ocr_json": raw_ocr_json,
            "llm_json": schema_v1,          # 保存 schema_v1（方便后面追溯/再跑规则）
            "schema_version": "v1",

            # business risk fields (你 invoices 表里有这些列)
            "expected_amount": expected_amount,
            "amount_diff": amount_diff,
            "risk_flag": int((schema_v1.get("risk") or {}).get("risk_flag") or 0),
            "risk_reason": (schema_v1.get("risk") or {}).get("risk_reason") or [],

            "unique_hash": unique_hash,
        }

        try:
            invoice_id = self.invoice_repo.insert_invoice(row)

            # 插入 items（兼容你 main.DB 没有 executemany 的情况）
            items = flat.get("invoice_items") or []
            if self.item_repo and isinstance(items, list) and items:
                try:
                    self.item_repo.insert_items(invoice_id, items)
                except AttributeError:
                    # fallback：逐条 insert
                    sql = """
                    INSERT INTO invoice_items(
                      invoice_id, item_name, item_spec, item_unit, item_quantity,
                      item_unit_price, item_amount, tax_rate, tax_amount
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """
                    for it in items:
                        self.item_repo.db.execute(sql, (
                            invoice_id,
                            it.get("item_name"),
                            it.get("item_spec"),
                            it.get("item_unit"),
                            it.get("item_quantity"),
                            it.get("item_unit_price"),
                            it.get("item_amount"),
                            it.get("tax_rate"),
                            it.get("tax_amount"),
                        ))

            # event（可选）
            if self.event_repo:
                try:
                    self.event_repo.add_event(invoice_id, "INGEST", "OK", payload={"source": source_file_path})
                except Exception:
                    pass

            return IngestResult(ok=True, action="inserted", invoice_id=invoice_id, unique_hash=unique_hash)

        except Exception as e:
            return IngestResult(ok=False, action="error", invoice_id=None, unique_hash=unique_hash, error=repr(e))


# =========================
# Pipeline entrypoints
# =========================
def run_pipeline_for_invoice_image(file_path: str, cfg: dict, svc: IngestionService) -> IngestResult:
    """
    真实流水线：图片 -> OCR(json) -> Dify workflow(json) -> MySQL -> (可选) Feishu
    + PO 对账风险：不一致则发邮件（抄送领导）
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    # 1) OCR
    raw_ocr_json = _call_ocr(file_path, cfg)
    logger.info("[DEBUG] raw_ocr_json head: %s", json.dumps(raw_ocr_json, ensure_ascii=False)[:800])
    ocr_text = (raw_ocr_json.get("extracted_text") or raw_ocr_json.get("text") or "").strip()

    # 2) Dify
    dify_key = _cfg_pick(cfg, ["dify_api_key", "DIFY_API_KEY"])
    dify_base = _cfg_pick(cfg, ["dify_base_url", "DIFY_BASE_URL"], "https://api.dify.ai/v1")
    workflow_id = _cfg_pick(cfg, ["dify_workflow_id", "DIFY_WORKFLOW_ID"])
    image_key = _cfg_pick(cfg, ["dify_image_key", "DIFY_IMAGE_KEY"], "invoice")

    outputs_schema_v1: Optional[Dict[str, Any]] = None
    flat_llm: Dict[str, Any] = {}

    if dify_key and workflow_id:
        try:
            dify = DifyClient(api_key=dify_key, base_url=dify_base)
            upload_id = dify.upload_file(file_path)
            file_input = DifyClient.build_file_input(upload_id, file_kind="image")

            dify_resp = None

            # ✅ 先 Array[File] 再 single File
            inputs_try_1 = {image_key: file_input, "ocr_text": ocr_text}
            inputs_try_2 = {image_key: [file_input], "ocr_text": ocr_text}

            # 504 重试（最多 3 次：你可用 cfg 调整）
            max_retry = int(_cfg_pick(cfg, ["DIFY_RETRY_MAX"], 3) or 3)
            sleep_sec = float(_cfg_pick(cfg, ["DIFY_RETRY_SLEEP_SEC"], 2) or 2)

            last_err = None
            for attempt in range(1, max_retry + 1):
                try:
                    try:
                        dify_resp = dify.run_workflow(workflow_id=workflow_id, inputs=inputs_try_1, timeout=180)
                    except Exception:
                        dify_resp = dify.run_workflow(workflow_id=workflow_id, inputs=inputs_try_2, timeout=180)
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    # 如果是 504，等一下重试
                    if "504" in repr(e):
                        logger.warning(f"[WARN] Dify 504 (attempt {attempt}/{max_retry}) -> retry after {sleep_sec}s")
                        time.sleep(sleep_sec)
                        continue
                    raise

            if last_err is not None:
                raise last_err

            outputs = (dify_resp.get("data") or {}).get("outputs") or {}
            logger.info("[DEBUG] dify outputs_keys: %s", list(outputs.keys()))

            # Dify 输出本来就是 schema_v1（invoice_meta/seller/...）
            outputs_schema_v1 = outputs if isinstance(outputs, dict) else None
            flat_llm = flatten_outputs(outputs_schema_v1 or {})
            logger.info("[DEBUG] flat_llm keys: %s", list(flat_llm.keys()))

        except Exception as e:
            logger.warning(f"[WARN] Dify failed -> use OCR fallback. err={repr(e)}")
            outputs_schema_v1 = None
            flat_llm = {}
    else:
        logger.warning("[WARN] Dify disabled (missing DIFY_API_KEY or DIFY_WORKFLOW_ID). Use OCR fallback.")
        outputs_schema_v1 = None
        flat_llm = {}

    # 2.1) 如果 Dify 失败：OCR 正则兜底（关键！避免“第二行基本空”）
    if outputs_schema_v1 is None or not isinstance(outputs_schema_v1, dict) or len(outputs_schema_v1) == 0:
        outputs_schema_v1 = _ocr_fallback_parse(ocr_text)
        flat_llm = flatten_outputs(outputs_schema_v1)

    # 3) PO 对账上下文（用于 risk_rules + email）
    purchase_no = _extract_purchase_no(cfg, file_path, ocr_text)

    po = None
    context: Dict[str, Any] = {}
    try:
        # repo.db 是 main.DB 适配器
        po = _fetch_purchase_order(svc.invoice_repo.db, purchase_no) if purchase_no else None
    except Exception:
        po = None

    if po:
        context = {
            "purchase_order_no": po.get("purchase_no"),
            "expected_amount_with_tax": po.get("expected_amount") or po.get("total_amount_with_tax"),
            "supplier_name_expected": po.get("supplier") or po.get("supplier_name"),
            "purchaser_name": po.get("purchaser_name"),
            "purchase_order_date": po.get("purchase_order_date"),
            "purchaser_email": po.get("purchaser_email"),
            "leader_email": po.get("leader_email"),
        }
    else:
        # 没 PO 不报错，只是不给 expected
        context = {"purchase_order_no": purchase_no}

    # 4) DB ingest
    result = svc.ingest_invoice(
        raw_ocr_json=raw_ocr_json,
        llm_json=outputs_schema_v1,
        source_file_path=file_path,
        context=context,
    )
    logger.info("[DB] result=%s", result)
    context["invoice_id"] = result.invoice_id
    context["unique_hash"] = result.unique_hash
    context["invoice_file_name"] = os.path.basename(file_path)
    context["amount_diff"] = _calc_amount_diff(
        context.get("expected_amount_with_tax"),
        flatten_outputs(outputs_schema_v1 or {}).get("total_amount_with_tax"),
    )

    # 5) Email alert (only send on a newly inserted risky invoice)
    if result.ok and result.action == "inserted":
        try:
            _send_risk_email_with_audit(
                outputs_schema_v1,
                context,
                cfg,
                db=getattr(svc.invoice_repo, "db", None),
                invoice_id=result.invoice_id,
            )
        except Exception as e:
            logger.warning(f"[WARN] Email alert failed (ignored): {repr(e)}")

    # 6) Feishu sync（可选）
    sync_mode = str(cfg.get("FEISHU_SYNC_MODE") or "off").lower()  # off / job / inline
    if sync_mode == "inline" and result.ok and result.action == "inserted":
        try:
            fields = _build_feishu_fields(outputs_schema_v1, context, result, file_path)
            ok, msg = _try_sync_to_feishu(cfg, fields)
            if ok:
                _record_feishu_sync(getattr(svc.invoice_repo, "db", None), result.invoice_id, response=msg)
                logger.info("[Feishu] inline sync ok invoice_id=%s", result.invoice_id)
            else:
                _record_feishu_sync(getattr(svc.invoice_repo, "db", None), result.invoice_id, error=msg)
                logger.warning("[WARN] Feishu inline sync failed: %s", msg)
        except Exception as e:
            _record_feishu_sync(getattr(svc.invoice_repo, "db", None), result.invoice_id, error=repr(e))
            logger.warning(f"[WARN] Feishu sync failed (ignored): {repr(e)}")

    return result


def process_one_image(file_path: str, cfg: dict, svc: IngestionService) -> IngestResult:
    """
    main.py 批处理入口会调这个
    """
    res = run_pipeline_for_invoice_image(file_path, cfg, svc)
    logger.info("[OK] %s action=%s invoice_id=%s unique_hash=%s",
                os.path.basename(file_path), res.action, res.invoice_id, res.unique_hash)
    return res
