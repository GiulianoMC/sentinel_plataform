import pytest
from fastapi.testclient import TestClient


def test_admin_list_users_success(client, admin_auth_headers, test_user, admin_user):
    response = client.get("/admin/users", headers=admin_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "users" in data
    assert data["total"] >= 2  # admin + test_user


def test_admin_list_users_unauthorized(client, auth_headers):
    response = client.get("/admin/users", headers=auth_headers)
    assert response.status_code == 403


def test_admin_list_users_unauthenticated(client):
    response = client.get("/admin/users")
    assert response.status_code == 401


def test_admin_update_role_success(client, admin_auth_headers, test_user):
    response = client.patch(
        f"/admin/users/{test_user.id}/role",
        json={"role": "admin"},
        headers=admin_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "admin"


def test_admin_update_role_invalid(client, admin_auth_headers, test_user):
    response = client.patch(
        f"/admin/users/{test_user.id}/role",
        json={"role": "invalid"},
        headers=admin_auth_headers
    )
    assert response.status_code == 400


def test_admin_update_own_role_forbidden(client, admin_auth_headers, admin_user):
    response = client.patch(
        f"/admin/users/{admin_user.id}/role",
        json={"role": "user"},
        headers=admin_auth_headers
    )
    assert response.status_code == 400


def test_admin_update_status_success(client, admin_auth_headers, test_user):
    response = client.patch(
        f"/admin/users/{test_user.id}/status",
        json={"is_active": False},
        headers=admin_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is False


def test_admin_update_own_status_forbidden(client, admin_auth_headers, admin_user):
    response = client.patch(
        f"/admin/users/{admin_user.id}/status",
        json={"is_active": False},
        headers=admin_auth_headers
    )
    assert response.status_code == 400


def test_admin_delete_user_success(client, admin_auth_headers, test_user):
    response = client.delete(f"/admin/users/{test_user.id}", headers=admin_auth_headers)
    assert response.status_code == 204


def test_admin_delete_own_user_forbidden(client, admin_auth_headers, admin_user):
    response = client.delete(f"/admin/users/{admin_user.id}", headers=admin_auth_headers)
    assert response.status_code == 400


def test_admin_delete_nonexistent(client, admin_auth_headers):
    response = client.delete("/admin/users/999", headers=admin_auth_headers)
    assert response.status_code == 404


def test_admin_delete_user_with_comments(client, admin_auth_headers, test_user, test_video, db_session):
    from datetime import datetime, timezone
    from app.models.VideoModel import Comment
    comment = Comment(
        id="comment-1",
        youtube_id=test_video.youtube_id,
        author="autor",
        text="comentário de teste",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    db_session.add(comment)
    db_session.commit()

    response = client.delete(f"/admin/users/{test_user.id}", headers=admin_auth_headers)
    assert response.status_code == 204

    from app.models.VideoModel import Video
    assert db_session.query(Video).filter(Video.youtube_id == test_video.youtube_id).first() is None
    assert db_session.query(Comment).filter(Comment.id == "comment-1").first() is None