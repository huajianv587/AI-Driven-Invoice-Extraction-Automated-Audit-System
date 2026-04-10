from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str, *, salt: Optional[str] = None) -> str:
    raw_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        (password or "").encode("utf-8"),
        raw_salt.encode("utf-8"),
        120_000,
    ).hex()
    return f"pbkdf2_sha256${raw_salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, salt, _ = stored_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    return hash_password(password, salt=salt) == stored_hash


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def session_expiry(hours: int) -> datetime:
    return now_utc() + timedelta(hours=int(hours))


def role_rank() -> Dict[str, int]:
    return {"reviewer": 10, "operator": 20, "admin": 30, "auditor": 40}


def can_access(required_role: str, actual_role: str) -> bool:
    return role_rank().get(actual_role, 0) >= role_rank().get(required_role, 0)
