from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Iterable, Optional


ROLE_ADMIN = "admin"
ROLE_REVIEWER = "reviewer"
ROLE_OPS = "ops"
VALID_ROLES = {ROLE_ADMIN, ROLE_REVIEWER, ROLE_OPS}


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}")


def hash_password(password: str, *, salt: Optional[str] = None, iterations: int = 390000) -> str:
    normalized = str(password or "")
    salt_value = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        normalized.encode("utf-8"),
        salt_value.encode("utf-8"),
        int(iterations),
    )
    return f"pbkdf2_sha256${int(iterations)}${salt_value}${base64.b64encode(digest).decode('ascii')}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, raw_iterations, salt_value, expected_digest = str(password_hash or "").split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hash_password(password, salt=salt_value, iterations=int(raw_iterations))
    return hmac.compare_digest(candidate, password_hash)


def create_access_token(
    *,
    user_id: int,
    email: str,
    role: str,
    full_name: str,
    secret: str,
    ttl_sec: int,
) -> tuple[str, int]:
    issued_at = int(time.time())
    expires_at = issued_at + int(ttl_sec)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(int(user_id)),
        "email": str(email or "").strip().lower(),
        "role": str(role or "").strip().lower(),
        "name": str(full_name or "").strip(),
        "iat": issued_at,
        "exp": expires_at,
        "type": "access",
    }
    header_part = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_part = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{header_part}.{payload_part}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_part}.{payload_part}.{_b64url_encode(signature)}", expires_at


def _decode_access_token_with_secret(token: str, secret: str) -> Optional[Dict[str, Any]]:
    try:
        header_part, payload_part, signature_part = str(token or "").split(".", 2)
        signing_input = f"{header_part}.{payload_part}".encode("utf-8")
        expected_signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_signature, _b64url_decode(signature_part)):
            return None
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
        if payload.get("type") != "access":
            return None
        if int(payload.get("exp") or 0) <= int(time.time()):
            return None
        if str(payload.get("role") or "").strip().lower() not in VALID_ROLES:
            return None
        return payload
    except Exception:
        return None


def decode_access_token(token: str, secret: str, old_secrets: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    for candidate_secret in [secret, *list(old_secrets)]:
        normalized = str(candidate_secret or "").strip()
        if not normalized:
            continue
        payload = _decode_access_token_with_secret(token, normalized)
        if payload:
            return payload
    return None


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
