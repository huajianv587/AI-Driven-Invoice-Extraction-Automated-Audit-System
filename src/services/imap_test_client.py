from __future__ import annotations

import imaplib
import re
import time
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from typing import List, Optional


HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class InboxMessage:
    uid: str
    subject: str
    body: str
    sent_at_epoch: Optional[float]


def _decode_part(part) -> str:
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        text = payload.decode(charset, errors="replace")
    except LookupError:
        text = payload.decode("utf-8", errors="replace")
    if part.get_content_type() == "text/html":
        text = HTML_TAG_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def _message_body(message) -> str:
    chunks: List[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() not in {"text/plain", "text/html"}:
                continue
            text = _decode_part(part)
            if text:
                chunks.append(text)
    else:
        text = _decode_part(message)
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


def _sent_at_epoch(message) -> Optional[float]:
    raw = str(message.get("date") or "").strip()
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).timestamp()
    except Exception:
        return None


class IMAPInboxChecker:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        *,
        use_ssl: bool = True,
        mailbox: str = "INBOX",
    ):
        self.host = str(host or "").strip()
        self.port = int(port)
        self.username = str(username or "").strip()
        self.password = str(password or "")
        self.use_ssl = bool(use_ssl)
        self.mailbox = str(mailbox or "INBOX").strip() or "INBOX"

    def _connect(self):
        client = imaplib.IMAP4_SSL(self.host, self.port) if self.use_ssl else imaplib.IMAP4(self.host, self.port)
        client.login(self.username, self.password)
        status, _ = client.select(self.mailbox, readonly=True)
        if status != "OK":
            raise RuntimeError(f"Unable to open IMAP mailbox {self.mailbox!r}.")
        return client

    def find_messages(
        self,
        *,
        after_epoch: float = 0.0,
        subject_contains: str = "",
        body_contains: str = "",
        limit: int = 20,
    ) -> List[InboxMessage]:
        client = self._connect()
        try:
            status, data = client.uid("search", None, "ALL")
            if status != "OK":
                raise RuntimeError("IMAP UID search failed.")
            raw_uids = (data[0] or b"").split()
            messages: List[InboxMessage] = []
            for raw_uid in raw_uids[-max(1, int(limit)) :]:
                status, rows = client.uid("fetch", raw_uid, "(RFC822)")
                if status != "OK":
                    continue
                raw_message = b""
                for row in rows or []:
                    if isinstance(row, tuple) and len(row) >= 2 and isinstance(row[1], (bytes, bytearray)):
                        raw_message = bytes(row[1])
                        break
                if not raw_message:
                    continue
                message = BytesParser(policy=policy.default).parsebytes(raw_message)
                subject = str(message.get("subject") or "").strip()
                body = _message_body(message)
                sent_at = _sent_at_epoch(message)
                if after_epoch and sent_at is not None and sent_at < after_epoch:
                    continue
                if subject_contains and subject_contains not in subject:
                    continue
                if body_contains and body_contains not in body:
                    continue
                messages.append(
                    InboxMessage(
                        uid=raw_uid.decode("ascii", errors="ignore"),
                        subject=subject,
                        body=body,
                        sent_at_epoch=sent_at,
                    )
                )
            messages.sort(key=lambda item: item.sent_at_epoch or 0.0)
            return messages
        finally:
            try:
                client.close()
            except Exception:
                pass
            try:
                client.logout()
            except Exception:
                pass

    def wait_for_message(
        self,
        *,
        after_epoch: float,
        subject_contains: str = "",
        body_contains: str = "",
        timeout_sec: int = 90,
        poll_interval_sec: int = 5,
        limit: int = 20,
    ) -> InboxMessage:
        deadline = time.time() + int(timeout_sec)
        while time.time() < deadline:
            matches = self.find_messages(
                after_epoch=after_epoch,
                subject_contains=subject_contains,
                body_contains=body_contains,
                limit=limit,
            )
            if matches:
                return matches[-1]
            time.sleep(max(1, int(poll_interval_sec)))
        raise RuntimeError(
            "No matching IMAP message arrived before timeout "
            f"(subject contains {subject_contains!r}, body contains {body_contains!r})."
        )
