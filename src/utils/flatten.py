from __future__ import annotations
from typing import Any, Dict, List

def flatten_json(data: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    items: Dict[str, Any] = {}
    for k, v in (data or {}).items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, dict):
            items.update(flatten_json(v, new_key, sep=sep))
        elif isinstance(v, list):
            # store list as-is; caller may json.dumps if needed
            items[new_key] = v
        else:
            items[new_key] = v
    return items

def build_feishu_fields_from_normalized(normalized: Dict[str, Any]) -> Dict[str, Any]:
    flat = flatten_json(normalized)
    # Common columns (customize freely)
    mapping = {
        "invoice_meta.invoice_code": "invoice_code",
        "invoice_meta.invoice_number": "invoice_number",
        "invoice_meta.invoice_date": "invoice_date",
        "invoice_meta.purchase_order_no": "purchase_order_no",
        "seller.name": "seller_name",
        "buyer.name": "buyer_name",
        "totals.total_amount_with_tax": "total_amount_with_tax",
        "totals.tax_amount": "tax_amount",
        "totals.currency": "currency",
        "risk.flag": "risk_flag",
        "risk.summary": "risk_summary",
    }
    out: Dict[str, Any] = {}
    for src, dst in mapping.items():
        if src in flat:
            out[dst] = flat[src]
    # preserve these raw blocks for audit / advanced tables
    out["invoice_items"] = normalized.get("invoice_items", [])
    out["staff"] = normalized.get("staff", {})
    out["risk_reason"] = (normalized.get("risk") or {}).get("reason")
    return out
