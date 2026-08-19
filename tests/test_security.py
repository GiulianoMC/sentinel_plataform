import pytest
from datetime import timedelta
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    create_token_pair,
    TokenData,
)


def test_hash_password():
    password = "minhasenha123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True


def test_verify_password_wrong():
    password = "minhasenha123"
    hashed = hash_password(password)
    assert verify_password("outrasenha", hashed) is False


def test_create_access_token():
    data = {"sub": "1", "role": "user"}
    token = create_access_token(data)
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_access_token_with_expiry():
    data = {"sub": "1", "role": "user"}
    token = create_access_token(data, expires_delta=timedelta(minutes=10))
    assert isinstance(token, str)


def test_create_refresh_token():
    data = {"sub": "1", "role": "user"}
    token = create_refresh_token(data)
    assert isinstance(token, str)
    assert len(token) > 0


def test_decode_token():
    data = {"sub": "1", "role": "user"}
    token = create_access_token(data)
    decoded = decode_token(token)
    assert isinstance(decoded, TokenData)
    assert decoded.sub == "1"
    assert decoded.role == "user"
    assert decoded.type == "access"


def test_decode_invalid_token():
    with pytest.raises(ValueError):
        decode_token("invalid.token.here")


def test_create_token_pair():
    pair = create_token_pair(1, "user")
    assert hasattr(pair, "access_token")
    assert hasattr(pair, "refresh_token")
    assert pair.access_token != pair.refresh_token


def test_token_expiration():
    import time
    data = {"sub": "1", "role": "user"}
    token = create_access_token(data, expires_delta=timedelta(seconds=1))
    time.sleep(2)  # Increased sleep time to ensure expiration
    with pytest.raises(ValueError):
        decode_token(token)