from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret-password")
    assert hashed != "s3cret-password"
    assert verify_password("s3cret-password", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip():
    token = create_access_token("user-123", extra={"role": "admin"})
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "admin"
