"""
Filtro por canal: registo com snippet, /video/list?channel_id, /video/channels
e backfill POST /reprocess/video-channels.
"""
from datetime import datetime
from unittest.mock import patch

import pytest

from app.models.VideoModel import Video
from app.utils import youtube_client


@pytest.fixture
def channel_videos(db_session, test_user):
    """Dois canais (A com 2 vídeos, B com 1) e um vídeo sem canal identificado."""
    videos = [
        Video(youtube_id="a1", titulo="A 1", channel_id="UC_A", channel_title="Canal A", user_id=test_user.id),
        Video(youtube_id="a2", titulo="A 2", channel_id="UC_A", channel_title="Canal A", user_id=test_user.id),
        Video(youtube_id="b1", titulo="B 1", channel_id="UC_B", channel_title="Canal B", user_id=test_user.id),
        Video(youtube_id="n1", titulo="Sem canal", channel_id=None, user_id=test_user.id),
    ]
    db_session.add_all(videos)
    db_session.commit()
    return videos


class _FakeYouTube:
    """Imita youtube_service.videos().list(...).execute() e regista as chamadas."""

    def __init__(self, items_by_id):
        self.items_by_id = items_by_id
        self.calls = []

    def videos(self):
        return self

    def list(self, part, id):
        self.calls.append(id)
        return self

    def execute(self):
        ids = self.calls[-1].split(",")
        return {"items": [self.items_by_id[i] for i in ids if i in self.items_by_id]}


def _item(video_id, channel_id, channel_title, title="Título", published="2024-03-01T10:00:00Z"):
    return {
        "id": video_id,
        "snippet": {"title": title, "channelId": channel_id, "channelTitle": channel_title, "publishedAt": published},
    }


# ---------------------------------------------------------------------------
# Registo grava canal
# ---------------------------------------------------------------------------

def test_register_video_persists_channel_from_snippet(client, auth_headers, db_session):
    snippet = {
        "title": "Título da API",
        "channel_id": "UC_X",
        "channel_title": "Canal X",
        "published_at": datetime(2024, 3, 1, 10, 0),
    }
    with patch.object(youtube_client, "fetch_video_snippet", return_value=snippet):
        response = client.post(
            "/video/register",
            json={"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers=auth_headers,
        )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["titulo"] == "Título da API"
    assert data["channel_id"] == "UC_X"
    assert data["channel_title"] == "Canal X"
    assert data["published_at"].startswith("2024-03-01T10:00:00")


def test_register_video_user_title_wins_but_channel_still_saved(client, auth_headers):
    snippet = {"title": "Título da API", "channel_id": "UC_X", "channel_title": "Canal X", "published_at": None}
    with patch.object(youtube_client, "fetch_video_snippet", return_value=snippet):
        response = client.post(
            "/video/register",
            json={"video_url": "https://youtu.be/dQw4w9WgXcQ", "titulo": "Meu título"},
            headers=auth_headers,
        )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["titulo"] == "Meu título"
    assert data["channel_id"] == "UC_X"


def test_register_video_without_api_leaves_channel_null(client, auth_headers):
    # YOUTUBE_API_KEY="" no conftest -> fetch_video_snippet devolve None
    response = client.post(
        "/video/register",
        json={"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["titulo"] == "Título Desconhecido"
    assert data["channel_id"] is None
    assert data["channel_title"] is None


# ---------------------------------------------------------------------------
# /video/list e /video/channels
# ---------------------------------------------------------------------------

def test_list_videos_filtered_by_channel(client, auth_headers, channel_videos):
    response = client.get("/video/list?channel_id=UC_A", headers=auth_headers)
    assert response.status_code == 200
    ids = {v["youtube_id"] for v in response.json()}
    assert ids == {"a1", "a2"}
    assert all(v["channel_title"] == "Canal A" for v in response.json())


def test_list_videos_without_filter_returns_all(client, auth_headers, channel_videos):
    response = client.get("/video/list", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 4


def test_list_videos_unknown_channel_is_empty(client, auth_headers, channel_videos):
    response = client.get("/video/list?channel_id=UC_ZZZ", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_channels_groups_and_counts(client, auth_headers, channel_videos):
    response = client.get("/video/channels", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    # Vídeo sem canal não aparece; ordenado por video_count desc
    assert [c["channel_id"] for c in data] == ["UC_A", "UC_B"]
    assert data[0] == {"channel_id": "UC_A", "channel_title": "Canal A", "video_count": 2}
    assert data[1]["video_count"] == 1


def test_list_channels_scoped_to_user(client, auth_headers, db_session, other_user):
    db_session.add(Video(youtube_id="o1", titulo="O", channel_id="UC_OTHER",
                         channel_title="Outro", user_id=other_user.id))
    db_session.commit()
    response = client.get("/video/channels", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_channels_unauthenticated(client):
    assert client.get("/video/channels").status_code == 401


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

def test_backfill_fills_only_missing_channels(client, auth_headers, db_session, channel_videos):
    fake = _FakeYouTube({"n1": _item("n1", "UC_N", "Canal N", title="Título real")})
    with patch.object(youtube_client, "get_youtube_service", return_value=fake):
        response = client.post("/reprocess/video-channels", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 1
    assert data["updated"] == 1
    assert data["not_found"] == 0
    # Só o vídeo sem canal foi pedido à API
    assert fake.calls == ["n1"]

    db_session.expire_all()
    video = db_session.query(Video).filter_by(youtube_id="n1").first()
    assert video.channel_id == "UC_N"
    assert video.channel_title == "Canal N"
    assert video.published_at == datetime(2024, 3, 1, 10, 0)
    # Título só é substituído se era o placeholder
    assert video.titulo == "Sem canal"


def test_backfill_replaces_unknown_title(client, auth_headers, db_session, test_user):
    db_session.add(Video(youtube_id="u1", titulo="Título Desconhecido", user_id=test_user.id))
    db_session.commit()
    fake = _FakeYouTube({"u1": _item("u1", "UC_U", "Canal U", title="Agora conhecido")})
    with patch.object(youtube_client, "get_youtube_service", return_value=fake):
        response = client.post("/reprocess/video-channels", headers=auth_headers)
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(Video).filter_by(youtube_id="u1").first().titulo == "Agora conhecido"


def test_backfill_force_refreshes_existing(client, auth_headers, db_session, channel_videos):
    fake = _FakeYouTube({
        "a1": _item("a1", "UC_A", "Canal A renomeado"),
        "a2": _item("a2", "UC_A", "Canal A renomeado"),
        "b1": _item("b1", "UC_B", "Canal B"),
        "n1": _item("n1", "UC_N", "Canal N"),
    })
    with patch.object(youtube_client, "get_youtube_service", return_value=fake):
        response = client.post("/reprocess/video-channels?force=true", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["updated"] == 4
    # 4 ids cabem num único lote de 50
    assert len(fake.calls) == 1 and set(fake.calls[0].split(",")) == {"a1", "a2", "b1", "n1"}
    db_session.expire_all()
    assert db_session.query(Video).filter_by(youtube_id="a1").first().channel_title == "Canal A renomeado"


def test_backfill_counts_videos_missing_on_youtube(client, auth_headers, db_session, channel_videos):
    fake = _FakeYouTube({})  # vídeo apagado/privado: API não devolve item
    with patch.object(youtube_client, "get_youtube_service", return_value=fake):
        response = client.post("/reprocess/video-channels", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["updated"] == 0 and data["not_found"] == 1
    db_session.expire_all()
    assert db_session.query(Video).filter_by(youtube_id="n1").first().channel_id is None


def test_backfill_batches_in_groups_of_50(client, auth_headers, db_session, test_user):
    ids = [f"v{i:03d}xxxxxxx"[:11] for i in range(60)]
    db_session.add_all([Video(youtube_id=i, titulo="t", user_id=test_user.id) for i in ids])
    db_session.commit()
    fake = _FakeYouTube({i: _item(i, "UC_BIG", "Grande") for i in ids})
    with patch.object(youtube_client, "get_youtube_service", return_value=fake):
        response = client.post("/reprocess/video-channels", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["updated"] == 60
    assert [len(c.split(",")) for c in fake.calls] == [50, 10]


def test_backfill_nothing_pending_does_not_call_api(client, auth_headers, db_session, test_user):
    db_session.add(Video(youtube_id="ok1", titulo="t", channel_id="UC_OK", user_id=test_user.id))
    db_session.commit()
    with patch.object(youtube_client, "get_youtube_service", return_value=None):
        response = client.post("/reprocess/video-channels", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_backfill_without_api_key_returns_503(client, auth_headers, channel_videos):
    with patch.object(youtube_client, "get_youtube_service", return_value=None):
        response = client.post("/reprocess/video-channels", headers=auth_headers)
    assert response.status_code == 503


def test_backfill_scoped_to_user(client, auth_headers, db_session, other_user):
    db_session.add(Video(youtube_id="o1", titulo="O", user_id=other_user.id))
    db_session.commit()
    fake = _FakeYouTube({"o1": _item("o1", "UC_O", "Outro")})
    with patch.object(youtube_client, "get_youtube_service", return_value=fake):
        response = client.post("/reprocess/video-channels", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert fake.calls == []


def test_backfill_specific_video_not_owned_404(client, auth_headers, other_user_video):
    response = client.post(
        f"/reprocess/video-channels?youtube_id={other_user_video.youtube_id}", headers=auth_headers
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# youtube_client helpers
# ---------------------------------------------------------------------------

def test_parse_youtube_datetime_to_naive_utc():
    assert youtube_client.parse_youtube_datetime("2024-03-01T10:00:00Z") == datetime(2024, 3, 1, 10, 0)
    assert youtube_client.parse_youtube_datetime("2024-03-01T12:00:00+02:00") == datetime(2024, 3, 1, 10, 0)
    assert youtube_client.parse_youtube_datetime(None) is None
    assert youtube_client.parse_youtube_datetime("lixo") is None


def test_fetch_video_snippets_dedupes_and_ignores_missing():
    fake = _FakeYouTube({"a": _item("a", "UC_A", "A")})
    with patch.object(youtube_client, "get_youtube_service", return_value=fake):
        result = youtube_client.fetch_video_snippets(["a", "a", "zzz", ""])
    assert set(result) == {"a"}
    assert result["a"]["channel_id"] == "UC_A"
    assert fake.calls == ["a,zzz"]
