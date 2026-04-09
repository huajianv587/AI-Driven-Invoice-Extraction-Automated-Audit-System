# src/services/risk_rules.py
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Any, Dict, List, Optional


def _to_decimal(x: Any) -> Optional[Decimal]:
    """
    将输入转换为 Decimal 以确保财务计算精度，替代原有的 float 处理。
    """
    if x is None or str(x).strip() == "":
        return None
    try:
        # 清理金额中的逗号、空格及货币符号
        clean_val = str(x).replace(",", "").replace("¥", "").replace("￥", "").strip()
        return Decimal(clean_val).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _safe_str(x: Any) -> str:
    """安全字符串转换"""
    if x is None:
        return ""
    return str(x).strip()


def _parse_date(date_str: Any) -> Optional[datetime]:
    """
    尝试多种格式解析日期字符串。
    """
    if not date_str:
        return None

    # 预处理：提取数字部分，兼容“2024年01月12日”等格式
    clean_date = _safe_str(date_str)
    m = re.search(r"(\d{4})[年\-\/\.](\d{1,2})[月\-\/\.](\d{1,2})", clean_date)
    if m:
        clean_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(clean_date, fmt)
        except ValueError:
            continue
    return None


@dataclass
class RiskResult:
    """风险计算结果模型"""
    risk_flag: int
    risk_reason: List[str]


class RiskRules:
    """
    企业级发票风险校验引擎（增强版）：
    1. 基础合规检查（代码/号码/明细）
    2. 财务精度校验（价税合计三者勾稽）
    3. 业务对账校验（金额/供应商匹配）
    4. 流程合规检查（发票日期 vs 采购日期）
    5. 准入风险检查（供应商黑名单）
    """

    def evaluate(self, invoice: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> RiskResult:
        context = context or {}
        reasons: List[str] = []

        # --- 1. 基础合规性检查 ---
        meta = invoice.get("invoice_meta") or {}
        code = _safe_str(meta.get("invoice_code"))
        num = _safe_str(meta.get("invoice_number"))
        if not code or not num:
            reasons.append("MissingInvoiceCodeOrNumber")

        items = invoice.get("invoice_items") or []
        if isinstance(items, list) and len(items) == 0:
            reasons.append("NoInvoiceItems")

        # --- 2. 财务勾稽精度校验 (Decimal 勾稽) ---
        totals = invoice.get("totals") or {}
        wot = _to_decimal(totals.get("total_amount_without_tax"))
        tax = _to_decimal(totals.get("total_tax_amount"))
        wit = _to_decimal(totals.get("total_amount_with_tax"))

        if wot is not None and tax is not None and wit is not None:
            # 允许 0.01 的精度偏差
            if abs((wot + tax) - wit) > Decimal("0.01"):
                reasons.append("AmountSumMismatch")

        # --- 3. 业务对账一致性校验 ---
        # 3.1 金额对账
        expected_amt = _to_decimal(context.get("expected_amount_with_tax"))
        if expected_amt is not None and wit is not None:
            if abs(expected_amt - wit) > Decimal("0.01"):
                reasons.append("AmountMismatchWithExpected")

        # 3.2 供应商名称匹配
        seller = invoice.get("seller") or {}
        seller_name = _safe_str(seller.get("seller_name"))
        expected_seller = _safe_str(context.get("supplier_name_expected"))
        if expected_seller and seller_name:
            if expected_seller not in seller_name and seller_name not in expected_seller:
                reasons.append("SellerNameMismatch")

        # --- 4. 流程与准入风控 (新增) ---
        # 4.1 日期倒挂校验：发票日期不能早于采购订单(PO)日期
        inv_date = _parse_date(meta.get("invoice_date"))
        po_date = _parse_date(context.get("purchase_order_date"))
        if inv_date and po_date:
            if inv_date < po_date:
                reasons.append("InvoiceDateEarlierThanPO")

        # 4.2 供应商黑名单校验
        blacklist = context.get("supplier_blacklist") or []
        if seller_name and any(bad_node in seller_name for bad_node in blacklist if bad_node):
            reasons.append("SupplierInBlacklist")

        # --- 结果汇总 ---
        risk_flag = 1 if len(reasons) > 0 else 0
        return RiskResult(risk_flag=risk_flag, risk_reason=reasons)

    def merge_into_invoice(self, invoice: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        运行校验并将结果合并回原始发票数据结构中。
        """
        res = self.evaluate(invoice, context)
        invoice["risk"] = {
            "risk_flag": res.risk_flag,
            "risk_reason": res.risk_reason
        }
        return invoice