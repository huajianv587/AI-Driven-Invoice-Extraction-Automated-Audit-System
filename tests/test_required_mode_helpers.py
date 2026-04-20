from __future__ import annotations

import datetime as dt
from email.message import EmailMessage

from src.services import feishu_bitable_client as feishu_mod
from src.services import imap_test_client as imap_mod
from src.services.risk_alert_service import RiskAlertService


def build_email(*, subject: str, body: str, sent_at: dt.datetime) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["Date"] = sent_at.strftime("%a, %d %b %Y %H:%M:%S +0000")
    message.set_content(body)
    return message.as_bytes()


class FakeIMAPClient:
    def __init__(self, messages: dict[bytes, bytes]):
        self.messages = messages

    def login(self, username: str, password: str):
        return "OK", [b"logged-in"]

    def select(self, mailbox: str, readonly: bool = True):
        return "OK", [b"selected"]

    def uid(self, command: str, *args):
        if command == "search":
            return "OK", [b" ".join(self.messages.keys())]
        if command == "fetch":
            uid = args[0]
            return "OK", [(b"RFC822", self.messages[uid])]
        raise AssertionError(f"Unexpected IMAP command: {command}")

    def close(self):
        return "OK", [b"closed"]

    def logout(self):
        return "BYE", [b"logout"]


class StubResponse:
    def __init__(self, status_code: int, payload=None, *, text: str | None = None, headers: dict | None = None, json_error: Exception | None = None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else str(payload)
        self.headers = headers or {}
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class NoopEmailClient:
    def send_text_email(self, *args, **kwargs):
        raise AssertionError("This test does not send email.")


def test_imap_checker_filters_by_subject_body_and_recency(monkeypatch):
    now = dt.datetime.utcnow().replace(microsecond=0)
    old_message = build_email(
        subject="[Invoice Risk Alert][OLD] PO:PO-DEMO Invoice:INV-1",
        body="Unique hash: hash-old",
        sent_at=now - dt.timedelta(days=2),
    )
    new_message = build_email(
        subject="[Invoice Risk Alert][REQ-SUCCESS] PO:PO-DEMO Invoice:INV-2",
        body="Unique hash: hash-new",
        sent_at=now,
    )
    monkeypatch.setattr(
        imap_mod.imaplib,
        "IMAP4_SSL",
        lambda host, port: FakeIMAPClient({b"1": old_message, b"2": new_message}),
    )

    checker = imap_mod.IMAPInboxChecker(
        host="imap.example.test",
        port=993,
        username="tester@example.test",
        password="secret",
    )
    matches = checker.find_messages(
        after_epoch=(now - dt.timedelta(hours=1)).timestamp(),
        subject_contains="REQ-SUCCESS",
        body_contains="hash-new",
        limit=10,
    )

    assert [message.uid for message in matches] == ["2"]
    assert matches[0].subject.endswith("Invoice:INV-2")
    assert "hash-new" in matches[0].body


def test_feishu_get_record_returns_payload(monkeypatch):
    monkeypatch.setattr(
        feishu_mod.requests,
        "get",
        lambda url, headers, timeout: StubResponse(
            200,
            {
                "code": 0,
                "data": {
                    "record": {
                        "record_id": "rec-test-1",
                        "fields": {"unique_hash": "hash-123"},
                    }
                },
            },
        ),
    )
    client = feishu_mod.FeishuBitableClient(
        app_id="app-id",
        app_secret="app-secret",
        app_token="app-token",
        table_id="table-id",
    )

    ok, payload = client.get_record("tenant-token", "rec-test-1")

    assert ok is True
    assert payload["data"]["record"]["fields"]["unique_hash"] == "hash-123"


def test_feishu_tenant_token_reports_http_and_body_preview_for_non_json_response(monkeypatch):
    monkeypatch.setattr(
        feishu_mod.requests,
        "post",
        lambda url, json, timeout: StubResponse(
            502,
            text="<html><body><h1>502 Bad Gateway</h1></body></html>",
            headers={"content-type": "text/html"},
            json_error=ValueError("not json"),
        ),
    )
    client = feishu_mod.FeishuBitableClient(
        app_id="app-id",
        app_secret="app-secret",
        app_token="app-token",
        table_id="table-id",
    )

    try:
        client.get_tenant_token()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected get_tenant_token() to raise for non-JSON response.")

    assert "HTTP 502" in message
    assert "non-JSON body" in message
    assert "text/html" in message
    assert "Bad Gateway" in message


def test_feishu_get_record_keeps_http_details_when_response_is_not_json(monkeypatch):
    monkeypatch.setattr(
        feishu_mod.requests,
        "get",
        lambda url, headers, timeout: StubResponse(
            502,
            text="<html><body>upstream failure</body></html>",
            headers={"content-type": "text/html"},
            json_error=ValueError("not json"),
        ),
    )
    client = feishu_mod.FeishuBitableClient(
        app_id="app-id",
        app_secret="app-secret",
        app_token="app-token",
        table_id="table-id",
    )

    ok, payload = client.get_record("tenant-token", "rec-test-1")

    assert ok is False
    assert payload["http_status"] == 502
    assert payload["content_type"] == "text/html"
    assert payload["body_preview"] == "<html><body>upstream failure</body></html>"


def test_risk_alert_content_includes_external_prefix_and_unique_hash():
    service = RiskAlertService(email_client=NoopEmailClient(), fallback_to="alerts@example.test")
    invoice = {
        "invoice_meta": {"invoice_code": "INV", "invoice_number": "001", "invoice_date": "2026-04-17"},
        "seller": {"seller_name": "Atlas Components Ltd"},
        "totals": {"total_amount_with_tax": 120.0},
        "risk": {"risk_flag": 1, "risk_reason": ["AmountMismatchWithExpected"]},
    }
    context = {
        "purchase_order_no": "PO-DEMO-001",
        "invoice_id": 8,
        "invoice_file_name": "invoice.jpg",
        "expected_amount_with_tax": 100.0,
        "amount_diff": 20.0,
        "unique_hash": "hash-required-1",
        "external_prefix": "REQUIRED-TEST-1",
    }

    subject = service._build_subject(invoice, context)
    body = service._build_content(invoice, context)

    assert "[REQUIRED-TEST-1]" in subject
    assert "Unique hash: hash-required-1" in body
    assert "External reference: REQUIRED-TEST-1" in body
