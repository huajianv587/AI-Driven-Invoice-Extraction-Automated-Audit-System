import smtplib
import socket
from dataclasses import dataclass
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any, Dict, List, Optional


@dataclass
class EmailSendResult:
    ok: bool
    error: Optional[str] = None
    smtp_code: Optional[int] = None
    smtp_message: Optional[str] = None


class EmailDeliveryChecker:
    """Thin SMTP client used by alerting and connectivity checks."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_pass: str,
        use_tls: bool = True,
        use_ssl: bool = False,
        timeout_sec: int = 20,
        from_name: str = "AI Invoice Audit System",
        from_email: Optional[str] = None,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = int(smtp_port)
        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass
        self.use_tls = use_tls
        self.use_ssl = use_ssl
        self.timeout_sec = timeout_sec
        self.from_name = from_name
        self.from_email = from_email or smtp_user or "noreply@invoice-audit.local"

    def check_connectivity(self) -> Dict[str, Any]:
        try:
            host_ip = socket.gethostbyname(self.smtp_host)
            sock = socket.create_connection((self.smtp_host, self.smtp_port), timeout=self.timeout_sec)
            sock.close()
            return {"ok": True, "host_ip": host_ip}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def send_text_email(
        self,
        to_email: str,
        subject: str,
        content: str,
        cc: Optional[List[str]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> EmailSendResult:
        cc = cc or []
        if not to_email:
            return EmailSendResult(ok=False, error="Missing recipient email address")

        recipients = [to_email] + cc
        msg = MIMEText(content, "plain", "utf-8")
        msg["From"] = formataddr((str(Header(self.from_name, "utf-8")), self.from_email))
        msg["To"] = to_email
        if cc:
            msg["Cc"] = ",".join(cc)
        msg["Subject"] = Header(subject, "utf-8")

        if extra_headers:
            for key, value in extra_headers.items():
                msg[key] = value

        server = None
        try:
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=self.timeout_sec)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout_sec)

            server.ehlo()
            if self.use_tls and not self.use_ssl:
                server.starttls()
                server.ehlo()

            if self.smtp_user and self.smtp_pass:
                server.login(self.smtp_user, self.smtp_pass)

            server.sendmail(self.from_email, recipients, msg.as_string())
            return EmailSendResult(ok=True)
        except smtplib.SMTPResponseException as exc:
            return EmailSendResult(
                ok=False,
                error=str(exc),
                smtp_code=getattr(exc, "smtp_code", None),
                smtp_message=str(getattr(exc, "smtp_error", b"").decode("utf-8", "ignore")),
            )
        except Exception as exc:
            return EmailSendResult(ok=False, error=str(exc))
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
