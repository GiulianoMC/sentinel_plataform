import pytest
from fastapi.testclient import TestClient


def test_analytics_summary_authenticated(client, auth_headers, test_video):
    response = client.get(f"/analytics/{test_video.youtube_id}/summary", headers=auth_headers)
    assert response.status_code == 200


def test_analytics_summary_unauthenticated(client, test_video):
    response = client.get(f"/analytics/{test_video.youtube_id}/summary")
    assert response.status_code == 401


def test_analytics_summary_not_owner(client, auth_headers, other_user_video):
    response = client.get(f"/analytics/{other_user_video.youtube_id}/summary", headers=auth_headers)
    assert response.status_code == 404


def test_analytics_intentions_authenticated(client, auth_headers, test_video):
    response = client.get(f"/analytics/{test_video.youtube_id}/intentions", headers=auth_headers)
    assert response.status_code == 200


def test_analytics_products_authenticated(client, auth_headers, test_video):
    response = client.get(f"/analytics/{test_video.youtube_id}/products", headers=auth_headers)
    assert response.status_code == 200


def test_analytics_sentiment_authenticated(client, auth_headers, test_video):
    response = client.get(f"/analytics/{test_video.youtube_id}/sentiment", headers=auth_headers)
    assert response.status_code == 200