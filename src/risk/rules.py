from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

@dataclass
class RiskHit:
    rule_id: str
    severity: str
    reason: str
    evidence: Optional[str] = None

def _to_float(x) -> Optional[float]:
    try:
        if x is None: 
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).replace(",", "").strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None

def apply_risk_rules(normalized: Dict[str, Any], expected_amount: Optional[float] = None) -> List[RiskHit]:
    hits: List[RiskHit] = []
    totals = normalized.get("totals", {}) or {}
    total_with_tax = _to_float(totals.get("total_amount_with_tax"))
    tax_amount = _to_float(totals.get("tax_amount"))
    total_wo_tax = _to_float(totals.get("total_amount_without_tax"))

    # R1: total consistency
    if total_with_tax is not None and tax_amount is not None and total_wo_tax is not None:
        if abs((total_wo_tax + tax_amount) - total_with_tax) > 0.02:
            hits.append(RiskHit(
                rule_id="R_TOTAL_TAX_MISMATCH",
                severity="HIGH",
                reason="价税合计不一致：不含税金额 + 税额 ≠ 含税金额",
                evidence=f"wo_tax={total_wo_tax}, tax={tax_amount}, with_tax={total_with_tax}"
            ))

    # R2: PO mismatch
    if expected_amount is not None and total_with_tax is not None:
        diff = total_with_tax - expected_amount
        if abs(diff) > max(1.0, expected_amount * 0.01):
            hits.append(RiskHit(
                rule_id="R_PO_AMOUNT_DIFF",
                severity="HIGH",
                reason="发票金额与采购订单预期金额不一致",
                evidence=f"expected={expected_amount}, actual={total_with_tax}, diff={diff}"
            ))

    # R3: missing key fields
    meta = normalized.get("invoice_meta", {}) or {}
    if not meta.get("invoice_number"):
        hits.append(RiskHit("R_MISSING_INVOICE_NO", "MEDIUM", "缺失发票号码", None))
    if not meta.get("invoice_date"):
        hits.append(RiskHit("R_MISSING_DATE", "LOW", "缺失开票日期", None))

    return hits
