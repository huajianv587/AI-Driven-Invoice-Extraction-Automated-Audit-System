import pytest

from src.api.security import create_access_token, decode_access_token, hash_password, verify_password
from src.api.state_machine import InvalidStateTransition, validate_review_transition


def test_password_hash_roundtrip():
    password_hash = hash_password("StrongPassw0rd!")
    assert verify_password("StrongPassw0rd!", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_access_token_roundtrip():
    token, expires_at = create_access_token(
        user_id=7,
        email="admin@example.com",
        role="admin",
        full_name="Admin User",
        secret="unit-test-secret",
        ttl_sec=600,
    )
    payload = decode_access_token(token, "unit-test-secret")
    assert payload is not None
    assert payload["sub"] == "7"
    assert payload["role"] == "admin"
    assert int(payload["exp"]) == expires_at


def test_access_token_rejects_tampering_expiry_and_unknown_roles():
    token, _ = create_access_token(
        user_id=7,
        email="admin@example.com",
        role="admin",
        full_name="Admin User",
        secret="unit-test-secret",
        ttl_sec=600,
    )
    header, payload, signature = token.split(".")
    tampered_signature = f"{'a' if signature[0] != 'a' else 'b'}{signature[1:]}"
    tampered = f"{header}.{payload}.{tampered_signature}"
    assert decode_access_token(tampered, "unit-test-secret") is None
    assert decode_access_token(token, "wrong-secret") is None

    expired, _ = create_access_token(
        user_id=7,
        email="admin@example.com",
        role="admin",
        full_name="Admin User",
        secret="unit-test-secret",
        ttl_sec=-1,
    )
    assert decode_access_token(expired, "unit-test-secret") is None

    unknown_role, _ = create_access_token(
        user_id=7,
        email="admin@example.com",
        role="owner",
        full_name="Admin User",
        secret="unit-test-secret",
        ttl_sec=600,
    )
    assert decode_access_token(unknown_role, "unit-test-secret") is None


def test_access_token_accepts_decode_only_old_secret():
    token, _ = create_access_token(
        user_id=7,
        email="admin@example.com",
        role="admin",
        full_name="Admin User",
        secret="old-secret",
        ttl_sec=600,
    )
    assert decode_access_token(token, "new-secret") is None
    payload = decode_access_token(token, "new-secret", old_secrets=["old-secret"])
    assert payload is not None
    assert payload["sub"] == "7"


def test_review_state_transition_matrix():
    validate_review_transition("Pending", "Approved", "reviewer")
    validate_review_transition("Rejected", "Pending", "admin")
    with pytest.raises(InvalidStateTransition):
        validate_review_transition("Approved", "Pending", "reviewer")
    with pytest.raises(InvalidStateTransition):
        validate_review_transition("Approved", "Approved", "reviewer")
