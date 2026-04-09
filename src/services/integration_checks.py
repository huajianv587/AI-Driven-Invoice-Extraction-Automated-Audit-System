from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests

from src.services.email_delivery_checker import EmailDeliveryChecker
from src.services.feishu_bitable_client import FeishuBitableClient


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str
    detail: Optional[str] = None


def check_http_endpoint(name: str, url: str, timeout: int = 8) -> CheckResult:
    try:
        resp = requests.get(url, timeout=timeout)
        return CheckResult(name=name, ok=True, message=f"HTTP {resp.status_code}", detail=url)
    except Exception as exc:
        return CheckResult(name=name, ok=False, message=str(exc), detail=url)


def check_dify(base_url: str, api_key: str, workflow_id: str) -> CheckResult:
    if not (base_url and api_key and workflow_id):
        return CheckResult(name="Dify", ok=False, message="Not configured")

    try:
        parsed = urlparse(base_url)
        probe_url = f"{parsed.scheme}://{parsed.netloc}/"
        resp = requests.get(probe_url, timeout=8)
        return CheckResult(name="Dify", ok=True, message=f"Reachable (HTTP {resp.status_code})", detail=probe_url)
    except Exception as exc:
        return CheckResult(name="Dify", ok=False, message=str(exc), detail=base_url)


def check_feishu(app_id: str, app_secret: str, app_token: str, table_id: str) -> CheckResult:
    if not (app_id and app_secret and app_token and table_id):
        return CheckResult(name="Feishu", ok=False, message="Not configured")

    try:
        client = FeishuBitableClient(
            app_id=app_id,
            app_secret=app_secret,
            app_token=app_token,
            table_id=table_id,
        )
        token = client.get_tenant_token()
        if token:
            return CheckResult(name="Feishu", ok=True, message="Tenant token acquired")
        return CheckResult(name="Feishu", ok=False, message="Tenant token empty")
    except Exception as exc:
        return CheckResult(name="Feishu", ok=False, message=str(exc))


def check_smtp(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    use_tls: bool,
    use_ssl: bool,
    from_name: str,
    from_email: str,
) -> CheckResult:
    if not smtp_host:
        return CheckResult(name="SMTP", ok=False, message="Not configured")

    checker = EmailDeliveryChecker(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_pass=smtp_pass,
        use_tls=use_tls,
        use_ssl=use_ssl,
        from_name=from_name,
        from_email=from_email or smtp_user or "noreply@invoice-audit.local",
    )
    result = checker.check_connectivity()
    if result.get("ok"):
        return CheckResult(name="SMTP", ok=True, message="Socket reachable", detail=result.get("host_ip"))
    return CheckResult(name="SMTP", ok=False, message=result.get("error", "Connectivity failed"))
