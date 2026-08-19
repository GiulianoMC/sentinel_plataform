import pytest
from fastapi.testclient import TestClient


import pytest
from fastapi.testclient import TestClient
from app.models.VideoModel import Video, Comment
from datetime import datetime


def test_analytics_overview_authenticated(client, auth_headers, test_video):
    response = client.get("/analytics/overview", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_videos"] == 1
    assert data["total_comments"] == 0
    assert data["analyzed_comments"] == 0
    assert data["average_sentiment"] is None
    assert data["videos"][0]["youtube_id"] == test_video.youtube_id
    assert data["videos"][0]["total_comments"] == 0
    assert data["videos"][0]["average_sentiment"] is None


def test_analytics_overview_unauthenticated(client, test_video):
    response = client.get("/analytics/overview")
    assert response.status_code == 401


def test_analytics_overview_scoped_to_user(client, auth_headers, test_video, other_user_video):
    response = client.get("/analytics/overview", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_videos"] == 1
    assert data["videos"][0]["youtube_id"] == test_video.youtube_id


def test_analytics_overview_with_comments(client, auth_headers, db_session, test_user):
    video = Video(
        youtube_id="overview_video",
        titulo="Overview Video",
        user_id=test_user.id
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)

    comments = [
        Comment(id="c1", youtube_id=video.youtube_id, author="a", text="t1",
                published_at=datetime.utcnow(), sentiment=4),
        Comment(id="c2", youtube_id=video.youtube_id, author="a", text="t2",
                published_at=datetime.utcnow(), sentiment=2),
        Comment(id="c3", youtube_id=video.youtube_id, author="a", text="t3",
                published_at=datetime.utcnow(), sentiment=None),
    ]
    db_session.add_all(comments)
    db_session.commit()

    response = client.get("/analytics/overview", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_videos"] == 1
    assert data["total_comments"] == 3
    assert data["analyzed_comments"] == 2
    assert data["average_sentiment"] == 3.0
    item = data["videos"][0]
    assert item["total_comments"] == 3
    assert item["analyzed_comments"] == 2
    assert item["average_sentiment"] == 3.0


def test_analytics_overview_weighted_average(client, auth_headers, db_session, test_user):
    video1 = Video(youtube_id="wv1", titulo="W Video 1", user_id=test_user.id)
    video2 = Video(youtube_id="wv2", titulo="W Video 2", user_id=test_user.id)
    db_session.add_all([video1, video2])
    db_session.commit()
    db_session.refresh(video1)
    db_session.refresh(video2)

    db_session.add_all([
        Comment(id="w1", youtube_id=video1.youtube_id, author="a", text="t",
                published_at=datetime.utcnow(), sentiment=2),
        Comment(id="w2", youtube_id=video1.youtube_id, author="a", text="t",
                published_at=datetime.utcnow(), sentiment=4),
        Comment(id="w3", youtube_id=video2.youtube_id, author="a", text="t",
                published_at=datetime.utcnow(), sentiment=5),
    ])
    db_session.commit()

    response = client.get("/analytics/overview", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["average_sentiment"] == 3.67  # (3*2 + 5*1) / 3
    by_id = {v["youtube_id"]: v for v in data["videos"]}
    assert by_id["wv1"]["average_sentiment"] == 3.0
    assert by_id["wv2"]["average_sentiment"] == 5.0


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