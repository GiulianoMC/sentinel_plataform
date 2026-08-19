import pytest
from fastapi.testclient import TestClient


def test_register_rate_limit(client):
    # Register endpoint has 5/min limit
    for i in range(5):
        response = client.post(
            "/auth/register",
            json={"email": f"user{i}@example.com", "password": "senha123"}
        )
        assert response.status_code == 201
    
    # 6th request should be rate limited
    response = client.post(
        "/auth/register",
        json={"email": "user6@example.com", "password": "senha123"}
    )
    assert response.status_code == 429


def test_login_rate_limit(client, test_user):
    # Login endpoint has 10/min limit
    for i in range(10):
        response = client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "senha123"}
        )
        # Some may fail due to wrong password, but shouldn't be rate limited
        assert response.status_code != 429
    
    # 11th request should be rate limited
    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "senha123"}
    )
    assert response.status_code == 429


def test_refresh_rate_limit(client, test_user):
    # First get a refresh token by registering a new user and logging in
    register_response = client.post(
        "/auth/register",
        json={"email": "refresh_test@example.com", "password": "senha123"}
    )
    assert register_response.status_code == 201
    refresh_token = register_response.json()["refresh_token"]
    
    # Refresh endpoint has 30/min limit
    for i in range(30):
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        if response.status_code == 200:
            refresh_token = response.json()["refresh_token"]
        assert response.status_code != 429
    
    # 31st request should be rate limited
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 429