from src.services.risk_rules import RiskRules


def test_risk_rules_detect_amount_mismatch() -> None:
    invoice = {
        "invoice_meta": {
            "invoice_code": "1234567890",
            "invoice_number": "12345678",
            "invoice_date": "2026-04-10",
        },
        "seller": {"seller_name": "ACME Supplier"},
        "totals": {
            "total_amount_without_tax": "100.00",
            "total_tax_amount": "10.00",
            "total_amount_with_tax": "110.00",
        },
        "invoice_items": [{"item_name": "service"}],
    }
    context = {
        "expected_amount_with_tax": "120.00",
        "supplier_name_expected": "ACME Supplier",
        "purchase_order_date": "2026-04-01",
    }
    result = RiskRules().evaluate(invoice, context)
    assert result.risk_flag == 1
    assert "AmountMismatchWithExpected" in result.risk_reason

