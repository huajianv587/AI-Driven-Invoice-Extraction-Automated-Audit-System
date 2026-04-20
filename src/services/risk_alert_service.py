from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .email_delivery_checker import EmailDeliveryChecker, EmailSendResult


RISK_REASON_LABELS = {
    "MissingInvoiceCodeOrNumber": "Invoice code or invoice number is missing",
    "NoInvoiceItems": "Invoice line items are missing",
    "AmountSumMismatch": "Subtotal + tax does not match invoice total",
    "AmountMismatchWithExpected": "Invoice total does not match the recorded purchase order amount",
    "SellerNameMismatch": "Invoice seller does not match the expected supplier",
    "InvoiceDateEarlierThanPO": "Invoice date is earlier than the purchase order date",
    "SupplierInBlacklist": "Supplier hit the configured blacklist",
}


@dataclass
class AlertResult:
    ok: bool
    sent: bool
    error: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None


class RiskAlertService:
    def __init__(
        self,
        email_client: EmailDeliveryChecker,
        fallback_to: str,
        anomaly_form_base_url: Optional[str] = None,
    ):
        self.email_client = email_client
        self.fallback_to = fallback_to
        self.anomaly_form_base_url = anomaly_form_base_url

    def _pick_recipients(self, context: Optional[Dict[str, Any]] = None) -> tuple[str, List[str]]:
        context = context or {}
        leader_email = (context.get("leader_email") or "").strip()
        to_email = (
            (context.get("purchaser_email") or "").strip()
            or (self.fallback_to or "").strip()
            or leader_email
        )

        cc_list: List[str] = []
        if leader_email and leader_email != to_email:
            cc_list.append(leader_email)

        return to_email, cc_list

    def _build_subject(self, invoice: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
        meta = invoice.get("invoice_meta") or {}
        po_no = (context or {}).get("purchase_order_no") or (context or {}).get("po_no") or "N/A"
        code = meta.get("invoice_code") or "UNKNOWN"
        number = meta.get("invoice_number") or "UNKNOWN"
        external_prefix = str((context or {}).get("external_prefix") or "").strip()
        prefix = f"[{external_prefix}]" if external_prefix else ""
        return f"[Invoice Risk Alert]{prefix} PO:{po_no} Invoice:{code}-{number}"

    def _format_amount(self, value: Any) -> str:
        try:
            return f"{float(value):.2f}"
        except (ValueError, TypeError):
            return str(value or "0.00")

    def _build_form_link(self, context: Optional[Dict[str, Any]] = None) -> str:
        if not self.anomaly_form_base_url:
            return ""

        context = context or {}
        url = urlparse(self.anomaly_form_base_url)
        query = dict(parse_qsl(url.query, keep_blank_values=True))

        for key in ("invoice_id", "purchase_order_no", "po_no", "unique_hash"):
            value = context.get(key)
            if value:
                query[key] = str(value)

        return urlunparse(url._replace(query=urlencode(query)))

    def _format_reasons(self, reasons: List[str]) -> List[str]:
        if not reasons:
            return ["No explicit reason was returned by the rule engine."]
        return [RISK_REASON_LABELS.get(reason, reason) for reason in reasons]

    def _build_content(self, invoice: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
        context = context or {}
        meta = invoice.get("invoice_meta") or {}
        seller = invoice.get("seller") or {}
        totals = invoice.get("totals") or {}
        risk = invoice.get("risk") or {}

        reason_lines = "\n".join(f"- {reason}" for reason in self._format_reasons(risk.get("risk_reason") or []))
        form_link = self._build_form_link(context)
        purchase_no = context.get("purchase_order_no") or context.get("po_no") or "N/A"
        purchaser_name = context.get("purchaser_name") or "N/A"
        external_prefix = str(context.get("external_prefix") or "").strip()
        unique_hash = str(context.get("unique_hash") or "").strip()
        prefix_line = f"External reference: {external_prefix}\n" if external_prefix else ""
        unique_hash_line = f"Unique hash: {unique_hash}\n" if unique_hash else ""
        form_line = f"\nWork order form: {form_link}" if form_link else ""

        return (
            "The invoice audit workflow detected a potential anomaly and needs manual review.\n\n"
            f"Purchase order: {purchase_no}\n"
            f"Purchaser: {purchaser_name}\n"
            f"Invoice ID: {context.get('invoice_id', 'N/A')}\n"
            f"Invoice file: {context.get('invoice_file_name', 'N/A')}\n\n"
            f"{prefix_line}"
            f"{unique_hash_line}"
            "Invoice summary:\n"
            f"- Invoice code: {meta.get('invoice_code', 'N/A')}\n"
            f"- Invoice number: {meta.get('invoice_number', 'N/A')}\n"
            f"- Invoice date: {meta.get('invoice_date', 'N/A')}\n"
            f"- Seller: {seller.get('seller_name', 'N/A')}\n"
            f"- Actual total: {self._format_amount(totals.get('total_amount_with_tax'))}\n"
            f"- Recorded PO total: {self._format_amount(context.get('expected_amount_with_tax'))}\n"
            f"- Amount diff: {self._format_amount(context.get('amount_diff'))}\n\n"
            f"Risk reasons:\n{reason_lines}"
            f"{form_line}\n"
        )

    def send_alert_if_needed(self, invoice: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> AlertResult:
        risk = invoice.get("risk") or {}
        risk_flag = int(risk.get("risk_flag") or 0)
        if risk_flag != 1:
            return AlertResult(ok=True, sent=False, detail={"message": "no risk"})

        to_email, cc_list = self._pick_recipients(context)
        if not to_email:
            return AlertResult(ok=False, sent=False, error="No recipient email configured")

        subject = self._build_subject(invoice, context)
        content = self._build_content(invoice, context)

        res: EmailSendResult = self.email_client.send_text_email(
            to_email=to_email,
            subject=subject,
            content=content,
            cc=cc_list,
        )

        detail = {
            "to": to_email,
            "cc": cc_list,
            "subject": subject,
            "form_link": self._build_form_link(context),
        }
        if res.ok:
            return AlertResult(ok=True, sent=True, detail=detail)
        return AlertResult(ok=False, sent=False, error=res.error, detail=detail)
