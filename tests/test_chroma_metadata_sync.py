"""Fase 2: write-back dos metadados de IA no ChromaDB."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import load_real_module, make_celery_stub, make_openai_stub


@pytest.fixture(scope="module")
def real_tasks():
    """app.celery.tasks real (o conftest mocka-o para não carregar o embedding)."""
    return load_real_module("real_celery_tasks", "app/celery/tasks.py",
                            stubs=make_celery_stub(), package="app.celery")


@pytest.fixture(scope="module")
def real_ai_tasks():
    stubs = {"openai": make_openai_stub()}
    stubs.update(make_celery_stub())
    return load_real_module(
        "real_celery_ai_tasks", "app/celery/ai_tasks.py", stubs=stubs, package="app.celery",
    )


# ------------------------------------------------------- build_chroma_metadata

def test_metadata_sem_analise_tem_apenas_video_id(real_tasks):
    assert real_tasks.build_chroma_metadata("v1") == {"video_id": "v1"}


def test_metadata_com_analise_completa(real_tasks):
    assert real_tasks.build_chroma_metadata("v1", 4, "Elogio", "Poco X8 Pro") == {
        "video_id": "v1", "sentiment": 4, "intent": "Elogio", "product": "poco x8 pro",
    }


def test_metadata_normaliza_produto_com_espacos(real_tasks):
    metadata = real_tasks.build_chroma_metadata("v1", 3, "Duvida", "  Poco X8 Pro ")
    assert metadata["product"] == "poco x8 pro"


def test_metadata_usa_sentinela_none_para_produto_nulo(real_tasks):
    """Chroma 0.4.15 não aceita None em metadados."""
    metadata = real_tasks.build_chroma_metadata("v1", 3, "Duvida", None)
    assert metadata["product"] == "none"
    assert None not in metadata.values()


def test_metadata_sentimento_zero_nao_e_tratado_como_ausente(real_tasks):
    # sentiment=0 não é válido na escala 1-5, mas o guard é `is not None`
    assert "sentiment" in real_tasks.build_chroma_metadata("v1", 0, None, None)


# ------------------------------------------- upsert não apaga a análise existente

def test_upsert_preserva_analise_ja_gravada(real_tasks, db_session, test_user):
    """Um retry da ingestão não pode sobrescrever os metadados de IA com só video_id."""
    from app.models.VideoModel import Comment, Video

    db_session.add(Video(youtube_id="upsert_video", titulo="Upsert", user_id=test_user.id))
    db_session.commit()
    db_session.add(Comment(id="up1", youtube_id="upsert_video", author="a", text="camera boa",
                           published_at=datetime(2026, 1, 1), sentiment=5, intent="Elogio",
                           product_mentioned="Poco X8 Pro"))
    db_session.commit()

    real_tasks.collection.upsert.reset_mock()
    with patch.object(real_tasks, "SessionLocal", return_value=db_session), \
         patch.object(db_session, "close"):
        real_tasks.processar_novo_comentario("up1", "camera boa", "upsert_video")

    metadata = real_tasks.collection.upsert.call_args.kwargs["metadatas"][0]
    assert metadata == {"video_id": "upsert_video", "sentiment": 5,
                        "intent": "Elogio", "product": "poco x8 pro"}


def test_upsert_de_comentario_novo_tem_apenas_video_id(real_tasks, db_session, test_user):
    from app.models.VideoModel import Video

    db_session.add(Video(youtube_id="novo_video", titulo="Novo", user_id=test_user.id))
    db_session.commit()

    real_tasks.collection.upsert.reset_mock()
    with patch.object(real_tasks, "SessionLocal", return_value=db_session), \
         patch.object(db_session, "close"):
        real_tasks.processar_novo_comentario("novo1", "texto novo", "novo_video",
                                             published_at="2026-01-01T00:00:00Z")

    assert real_tasks.collection.upsert.call_args.kwargs["metadatas"][0] == {"video_id": "novo_video"}


def test_sync_chroma_metadata_atualiza_metadados(real_tasks):
    real_tasks.collection.update.reset_mock()
    real_tasks.sync_chroma_metadata("c9", "v9", 2, "Critica", "Redmi Note 14")

    assert real_tasks.collection.update.call_args.kwargs["ids"] == ["c9"]
    assert real_tasks.collection.update.call_args.kwargs["metadatas"][0]["sentiment"] == 2


# --------------------------------------------------- disparo após análise de IA

def test_process_comments_with_ai_dispara_sync(real_ai_tasks, db_session, test_user):
    from app.models.VideoModel import Comment, Video

    db_session.add(Video(youtube_id="sync_video", titulo="Sync", user_id=test_user.id))
    db_session.commit()
    db_session.add(Comment(id="sync_c1", youtube_id="sync_video", author="a",
                           text="ótimo produto", published_at=datetime(2026, 1, 1)))
    db_session.commit()

    analise = MagicMock(sentiment=5, intent="Elogio", product_mentioned="Poco X8 Pro")
    real_ai_tasks.llm_service.analyze_comment.return_value = analise

    real_ai_tasks.celery.send_task.reset_mock()
    with patch.object(real_ai_tasks, "SessionLocal", return_value=db_session), \
         patch.object(db_session, "close"):
        real_ai_tasks.process_comments_with_ai("sync_c1", "ótimo produto")

    real_ai_tasks.celery.send_task.assert_called_once_with(
        "app.celery.tasks.sync_chroma_metadata",
        args=["sync_c1", "sync_video", 5, "Elogio", "Poco X8 Pro"],
    )


# ------------------------------------------------------------------ backfill

@pytest.fixture
def videos_para_backfill(db_session, test_user, other_user):
    from app.models.VideoModel import Comment, Video

    db_session.add_all([
        Video(youtube_id="meu_video", titulo="Meu", user_id=test_user.id),
        Video(youtube_id="video_alheio", titulo="Alheio", user_id=other_user.id),
    ])
    db_session.commit()

    db_session.add_all([
        Comment(id="b1", youtube_id="meu_video", author="a", text="t",
                published_at=datetime(2026, 1, 1), sentiment=4, intent="Elogio"),
        Comment(id="b2", youtube_id="meu_video", author="a", text="t",
                published_at=datetime(2026, 1, 2), sentiment=None),
        Comment(id="b3", youtube_id="video_alheio", author="a", text="t",
                published_at=datetime(2026, 1, 3), sentiment=2, intent="Critica"),
    ])
    db_session.commit()


def test_backfill_enfileira_apenas_analisados_do_usuario(db_session, test_user, videos_para_backfill):
    from app.use_cases.Insights.backfill_chroma_metadata import backfill_chroma_metadata_use_case
    from app.celery.celery_app import celery

    celery.send_task.reset_mock()
    resultado = backfill_chroma_metadata_use_case(db_session, user_id=test_user.id)

    assert resultado["enqueued"] == 1
    ids_enfileirados = [c.kwargs["args"][0] for c in celery.send_task.call_args_list]
    assert ids_enfileirados == ["b1"]


def test_backfill_restrito_a_um_video(db_session, test_user, videos_para_backfill):
    from app.use_cases.Insights.backfill_chroma_metadata import backfill_chroma_metadata_use_case
    from app.celery.celery_app import celery

    celery.send_task.reset_mock()
    resultado = backfill_chroma_metadata_use_case(db_session, youtube_id="meu_video",
                                                  user_id=test_user.id)

    assert resultado["enqueued"] == 1
    assert celery.send_task.call_args.kwargs["args"] == ["b1", "meu_video", 4, "Elogio", None]


def test_backfill_usuario_sem_videos(db_session, other_user):
    from app.use_cases.Insights.backfill_chroma_metadata import backfill_chroma_metadata_use_case
    from app.models.UserModel import User
    from app.core.security import hash_password

    sozinho = User(email="sozinho@example.com", hashed_password=hash_password("x"),
                   role="user", is_active=True)
    db_session.add(sozinho)
    db_session.commit()

    assert backfill_chroma_metadata_use_case(db_session, user_id=sozinho.id)["enqueued"] == 0


def test_endpoint_backfill_404_em_video_alheio(client, auth_headers, other_user_video):
    response = client.post("/reprocess/chroma-metadata?youtube_id=other_video_id",
                           headers=auth_headers)
    assert response.status_code == 404


def test_endpoint_backfill_do_proprio_video(client, auth_headers, videos_para_backfill):
    from app.celery.celery_app import celery

    celery.send_task.reset_mock()
    response = client.post("/reprocess/chroma-metadata?youtube_id=meu_video", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["enqueued"] == 1
