# src/utils/hash_utils.py
from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Optional


def _norm(s: Optional[str]) -> str:
    """Normalize strings: strip, upper, empty->'' """
    if s is None:
        return ""
    return str(s).strip().upper()


def _norm_money(x) -> str:
    """Normalize money to fixed string to reduce float noise."""
    if x is None or x == "":
        return ""
    try:
        d = Decimal(str(x)).quantize(Decimal("0.01"))
        return format(d, "f")
    except Exception:
        return str(x).strip()


def build_invoice_unique_hash(
    invoice_code: Optional[str],
    invoice_number: Optional[str],
    invoice_date: Optional[str],  # YYYY-MM-DD preferred
    seller_tax_id: Optional[str],
    total_amount_with_tax,
) -> str:
    """
    企业级去重推荐 hash：
    invoice_code + invoice_number + invoice_date + seller_tax_id + total_amount_with_tax

    为什么这样：
    - code+number 是强唯一，但OCR有时缺失/错读
    - 加 date / seller_tax_id / amount 可提高鲁棒性
    """
    parts = [
        _norm(invoice_code),
        _norm(invoice_number),
        _norm(invoice_date),
        _norm(seller_tax_id),
        _norm_money(total_amount_with_tax),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
