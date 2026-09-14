"""
Analytics por canal: overview filtrado, /analytics/channels e as quatro
métricas em /analytics/channels/{channel_id}/...
"""
from datetime import datetime

import pytest

from app.models.VideoModel import Video, Comment


def _c(cid, youtube_id, sentiment=None, intent=None, product=None):
    return Comment(id=cid, youtube_id=youtube_id, author="a", text="t", published_at=datetime.utcnow(),
                   sentiment=sentiment, intent=intent, product_mentioned=product)


@pytest.fixture
def channel_data(db_session, test_user, other_user):
    """
    Canal A: 2 vídeos (a1: 3 comentários, a2: 1). Canal B: 1 vídeo (b1: 2).
    Sem canal: n1 (1 comentário). Outro utilizador também tem vídeo no canal A
    (não pode contar).
    """
    db_session.add_all([
        Video(youtube_id="a1", titulo="A 1", channel_id="UC_A", channel_title="Canal A", user_id=test_user.id),
        Video(youtube_id="a2", titulo="A 2", channel_id="UC_A", channel_title="Canal A", user_id=test_user.id),
        Video(youtube_id="b1", titulo="B 1", channel_id="UC_B", channel_title="Canal B", user_id=test_user.id),
        Video(youtube_id="n1", titulo="Sem canal", user_id=test_user.id),
        Video(youtube_id="o1", titulo="Outro no canal A", channel_id="UC_A", channel_title="Canal A",
              user_id=other_user.id),
    ])
    db_session.commit()
    db_session.add_all([
        _c("a1c1", "a1", sentiment=5, intent="Elogio", product="Produto X"),
        _c("a1c2", "a1", sentiment=3, intent="Duvida", product="produto x "),
        _c("a1c3", "a1", sentiment=None),
        _c("a2c1", "a2", sentiment=1, intent="Reclamacao", product="Produto Y"),
        _c("b1c1", "b1", sentiment=4, intent="Elogio"),
        _c("b1c2", "b1", sentiment=4, intent="Elogio"),
        _c("n1c1", "n1", sentiment=2, intent="Reclamacao"),
        _c("o1c1", "o1", sentiment=1, intent="Reclamacao", product="Produto X"),
    ])
    db_session.commit()


# ---------------------------------------------------------------------------
# /analytics/overview?channel_id=
# ---------------------------------------------------------------------------

def test_overview_without_filter_includes_channel_fields(client, auth_headers, channel_data):
    response = client.get("/analytics/overview", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] is None
    assert data["total_videos"] == 4
    assert data["total_comments"] == 7
    by_id = {v["youtube_id"]: v for v in data["videos"]}
    assert by_id["a1"]["channel_id"] == "UC_A"
    assert by_id["a1"]["channel_title"] == "Canal A"
    assert by_id["n1"]["channel_id"] is None


def test_overview_filtered_by_channel(client, auth_headers, channel_data):
    response = client.get("/analytics/overview?channel_id=UC_A", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] == "UC_A"
    assert data["total_videos"] == 2
    assert data["total_comments"] == 4
    assert data["analyzed_comments"] == 3
    # (5 + 3 + 1) / 3
    assert data["average_sentiment"] == 3.0
    assert {v["youtube_id"] for v in data["videos"]} == {"a1", "a2"}


def test_overview_filtered_by_unknown_channel_is_empty(client, auth_headers, channel_data):
    response = client.get("/analytics/overview?channel_id=UC_NOPE", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_videos"] == 0 and data["videos"] == []
    assert data["average_sentiment"] is None


# ---------------------------------------------------------------------------
# /analytics/channels
# ---------------------------------------------------------------------------

def test_channels_overview_aggregates_per_channel(client, auth_headers, channel_data):
    response = client.get("/analytics/channels", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_channels"] == 2
    assert data["videos_without_channel"] == 1
    # Mais comentários primeiro
    assert [c["channel_id"] for c in data["channels"]] == ["UC_A", "UC_B"]
    a = data["channels"][0]
    assert a["channel_title"] == "Canal A"
    assert a["total_videos"] == 2
    assert a["total_comments"] == 4
    assert a["analyzed_comments"] == 3
    assert a["average_sentiment"] == 3.0
    b = data["channels"][1]
    assert b["total_videos"] == 1 and b["total_comments"] == 2 and b["average_sentiment"] == 4.0


def test_channels_overview_empty_user(client, auth_headers):
    response = client.get("/analytics/channels", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"total_channels": 0, "videos_without_channel": 0, "channels": []}


def test_channels_overview_unauthenticated(client):
    assert client.get("/analytics/channels").status_code == 401


# ---------------------------------------------------------------------------
# /analytics/channels/{channel_id}/*
# ---------------------------------------------------------------------------

def test_channel_summary(client, auth_headers, channel_data):
    response = client.get("/analytics/channels/UC_A/summary", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] == "UC_A"
    assert data["channel_title"] == "Canal A"
    assert data["total_videos"] == 2
    assert data["total_comments"] == 4
    assert data["analyzed_comments"] == 3
    assert data["average_sentiment"] == 3.0


def test_channel_summary_ignores_other_users_videos_in_same_channel(client, auth_headers, channel_data):
    # other_user tem o1 no canal A com sentiment=1; se vazasse, a média cairia para 2.5
    data = client.get("/analytics/channels/UC_A/summary", headers=auth_headers).json()
    assert data["average_sentiment"] == 3.0
    assert data["total_videos"] == 2


def test_channel_intentions(client, auth_headers, channel_data):
    response = client.get("/analytics/channels/UC_A/intentions", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] == "UC_A"
    counts = {i["intent"]: i["count"] for i in data["intentions"]}
    assert counts == {"Elogio": 1, "Duvida": 1, "Reclamacao": 1}


def test_channel_products_normalized_across_videos(client, auth_headers, channel_data):
    response = client.get("/analytics/channels/UC_A/products?limit=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    products = {p["product_name"]: p for p in data["products"]}
    # 'Produto X' e 'produto x ' consolidam; o do other_user não entra
    assert products["produto x"]["count"] == 2
    assert products["produto x"]["average_sentiment"] == 4.0
    assert products["produto y"]["count"] == 1


def test_channel_products_min_mentions(client, auth_headers, channel_data):
    data = client.get("/analytics/channels/UC_A/products?min_mentions=2", headers=auth_headers).json()
    assert [p["product_name"] for p in data["products"]] == ["produto x"]


def test_channel_sentiment_distribution(client, auth_headers, channel_data):
    response = client.get("/analytics/channels/UC_A/sentiment", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] == "UC_A"
    assert data["distribution"] == {"1": 1, "2": 0, "3": 1, "4": 0, "5": 1}


@pytest.mark.parametrize("metric", ["summary", "intentions", "products", "sentiment"])
def test_channel_metrics_404_for_channel_without_own_videos(client, auth_headers, channel_data, metric):
    # UC_ONLY_OTHER só existe para o other_user
    assert client.get(f"/analytics/channels/UC_NOPE/{metric}", headers=auth_headers).status_code == 404


@pytest.mark.parametrize("metric", ["summary", "intentions", "products", "sentiment"])
def test_channel_metrics_404_when_only_other_user_has_channel(client, auth_headers, db_session, other_user, metric):
    db_session.add(Video(youtube_id="o9", titulo="O", channel_id="UC_ONLY_OTHER", user_id=other_user.id))
    db_session.commit()
    assert client.get(f"/analytics/channels/UC_ONLY_OTHER/{metric}", headers=auth_headers).status_code == 404


@pytest.mark.parametrize("metric", ["summary", "intentions", "products", "sentiment"])
def test_channel_metrics_unauthenticated(client, metric):
    assert client.get(f"/analytics/channels/UC_A/{metric}").status_code == 401


def test_per_video_endpoints_still_work(client, auth_headers, channel_data):
    """O refactor do repositório não pode alterar as respostas por vídeo."""
    summary = client.get("/analytics/a1/summary", headers=auth_headers).json()
    assert summary == {"youtube_id": "a1", "total_comments": 3, "analyzed_comments": 2, "average_sentiment": 4.0}
    sentiment = client.get("/analytics/a1/sentiment", headers=auth_headers).json()
    assert sentiment["distribution"] == {"1": 0, "2": 0, "3": 1, "4": 0, "5": 1}
    products = client.get("/analytics/a1/products", headers=auth_headers).json()
    assert products["products"][0] == {"product_name": "produto x", "count": 2, "average_sentiment": 4.0}
