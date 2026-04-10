from src.product.security import hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    password = "reviewer123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong-password", hashed) is False

