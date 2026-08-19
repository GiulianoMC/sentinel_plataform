import pytest
from fastapi.testclient import TestClient


def test_register_video_authenticated(client, auth_headers):
    response = client.post(
        "/video/register",
        json={"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        headers=auth_headers
    )
    # May fail due to no YouTube API key, but should not be 401
    assert response.status_code != 401


def test_register_video_unauthenticated(client):
    response = client.post(
        "/video/register",
        json={"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )
    assert response.status_code == 401


def test_list_videos_authenticated(client, auth_headers, test_video):
    response = client.get("/video/list", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["youtube_id"] == "test_video_id"


def test_list_videos_unauthenticated(client):
    response = client.get("/video/list")
    assert response.status_code == 401


def test_list_videos_only_own(client, auth_headers, other_user_video):
    response = client.get("/video/list", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    # Should only see own video, not other user's video
    assert len(data) == 0


def test_delete_video_authenticated_owner(client, auth_headers, test_video):
    response = client.delete(f"/video/{test_video.youtube_id}", headers=auth_headers)
    assert response.status_code == 200


def test_delete_video_unauthenticated(client, test_video):
    response = client.delete(f"/video/{test_video.youtube_id}")
    assert response.status_code == 401


def test_delete_video_not_owner(client, auth_headers, other_user_video):
    response = client.delete(f"/video/{other_user_video.youtube_id}", headers=auth_headers)
    assert response.status_code == 404


def test_delete_video_nonexistent(client, auth_headers):
    response = client.delete("/video/nonexistent", headers=auth_headers)
    assert response.status_code == 404