# src/utils/hash_utils.py
import hashlib
import json
import re
from typing import Any, Dict, Optional


def _norm(s: Optional[Any]) -> str:
    """把字符串做强归一化，减少空格/换行/全角空格导致的抖动"""
    if s is None:
        return ""
    s = str(s).strip()
    # 去掉所有空白（空格、换行、tab、全角空格等）
    s = re.sub(r"\s+", "", s)
    return s


def build_invoice_unique_hash(llm_json: Dict[str, Any], raw_ocr_json: Optional[Dict[str, Any]] = None) -> str:
    """
    稳定幂等 hash：
    - 优先：invoice_code + invoice_number (+ invoice_date) (+ seller_tax_id) (+ total_amount_with_tax)
      这些字段最稳定，不要用地址/人员/items 这种会抖动的字段。
    - 退化：如果拿不到 code/number，用 OCR 文本（强归一化后）hash。
    """
    llm_json = llm_json or {}

    invoice_meta = llm_json.get("invoice_meta") or {}
    seller = llm_json.get("seller") or {}
    buyer = llm_json.get("buyer") or {}
    totals = llm_json.get("totals") or {}

    invoice_code = _norm(invoice_meta.get("invoice_code"))
    invoice_number = _norm(invoice_meta.get("invoice_number"))
    invoice_date = _norm(invoice_meta.get("invoice_date"))

    seller_tax_id = _norm(seller.get("seller_tax_id"))
    buyer_tax_id = _norm(buyer.get("buyer_tax_id"))

    total_with_tax = totals.get("total_amount_with_tax")
    total_with_tax_str = "" if total_with_tax is None else _norm(total_with_tax)

    # ✅ 稳定业务主键优先
    if invoice_code and invoice_number:
        biz_key = "|".join([
            invoice_code,
            invoice_number,
            invoice_date,
            seller_tax_id,
            buyer_tax_id,
            total_with_tax_str,
        ])
        return hashlib.sha256(biz_key.encode("utf-8")).hexdigest()

    # ✅ 退化：OCR 文本（不同 OCR 返回结构也能兜底）
    ocr_text = ""
    if raw_ocr_json:
        if isinstance(raw_ocr_json, dict):
            # 你 OCR 若有 text 字段就用；否则把整个 json dump 成文本
            ocr_text = raw_ocr_json.get("text") or json.dumps(raw_ocr_json, ensure_ascii=False, sort_keys=True)
        else:
            ocr_text = str(raw_ocr_json)

    ocr_text = _norm(ocr_text)
    return hashlib.sha256(ocr_text.encode("utf-8")).hexdigest()


