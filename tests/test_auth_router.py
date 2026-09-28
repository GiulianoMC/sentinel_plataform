import pytest
from fastapi.testclient import TestClient


def test_register_user(client):
    response = client.post(
        "/auth/register",
        json={"email": "newuser@example.com", "password": "senha123"}
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["email"] == "newuser@example.com"
    assert data["role"] == "user"


def test_register_duplicate_email(client, test_user):
    response = client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "senha123"}
    )
    assert response.status_code == 400
    assert "já cadastrado" in response.json()["detail"]


def test_register_invalid_email(client):
    response = client.post(
        "/auth/register",
        json={"email": "invalid-email", "password": "senha123"}
    )
    assert response.status_code == 422


def test_register_short_password(client):
    response = client.post(
        "/auth/register",
        json={"email": "new@example.com", "password": "123"}
    )
    assert response.status_code == 422


def test_login_user(client, test_user):
    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "senha123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client, test_user):
    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401


def test_login_nonexistent_user(client):
    response = client.post(
        "/auth/login",
        json={"email": "nonexistent@example.com", "password": "senha123"}
    )
    assert response.status_code == 401


def test_login_inactive_user(client, db_session, test_user):
    test_user.is_active = False
    db_session.commit()
    
    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "senha123"}
    )
    assert response.status_code == 401


def test_refresh_token(client, test_user):
    # First login to get refresh token
    login_response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "senha123"}
    )
    refresh_token = login_response.json()["refresh_token"]
    
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    # New refresh token should be different
    assert data["refresh_token"] != refresh_token


def test_refresh_token_invalid(client):
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": "invalid.token.here"}
    )
    assert response.status_code == 401


def test_refresh_token_revoked(client, db_session, test_user):
    from app.models.UserModel import RevokedToken
    from app.core.security import decode_token, create_refresh_token
    from datetime import datetime, timezone
    
    # Create a refresh token and revoke it
    refresh_token = create_refresh_token({"sub": str(test_user.id), "role": "user"})
    payload = decode_token(refresh_token)
    
    revoked = RevokedToken(jti=payload.jti, expires_at=datetime.fromtimestamp(payload.exp, tz=timezone.utc))
    db_session.add(revoked)
    db_session.commit()
    
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 401


def test_logout(client, test_user, auth_headers):
    # Login to get refresh token
    login_response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "senha123"}
    )
    refresh_token = login_response.json()["refresh_token"]
    
    response = client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
        headers=auth_headers
    )
    assert response.status_code == 204


def test_me(client, test_user, auth_headers):
    response = client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["role"] == "user"
    assert data["id"] == test_user.id


def test_me_unauthorized(client):
    response = client.get("/auth/me")
    assert response.status_code == 401