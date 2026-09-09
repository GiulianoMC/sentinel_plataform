"""Fase 5: cache dos cards de insights, staleness e geração sem duplicação."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.VideoInsightModel import CARD_KINDS, VideoInsight
from app.models.VideoModel import Comment, Video
from app.use_cases.Insights.insight_cards import (
    GENERATION_LOCK_MINUTES,
    MIN_ANALYZED_TO_GENERATE,
    is_stale,
)


# ------------------------------------------------------------------ is_stale

@pytest.mark.parametrize("analisados_agora,na_geracao,esperado", [
    (0, 0, False),      # vídeo vazio: nada a gerar
    (5, 0, True),       # primeira geração
    (3, 3, False),      # sem novidade
    (13, 3, False),     # +10 exatos ainda não passa do piso
    (14, 3, True),      # acima do piso de 10
    (120, 100, False),  # +20% exatos: ainda não
    (121, 100, True),   # acima de +20%
])
def test_is_stale(analisados_agora, na_geracao, esperado):
    assert is_stale(analisados_agora, na_geracao) is esperado


# ------------------------------------------------------------------ fixtures

@pytest.fixture
def video_com_analisados(db_session, test_user):
    """Vídeo com 12 comentários analisados (acima do mínimo para gerar)."""
    db_session.add(Video(youtube_id="cards_video", titulo="Cards", user_id=test_user.id))
    db_session.commit()

    base = datetime(2026, 1, 1)
    db_session.add_all([
        Comment(id=f"k{i}", youtube_id="cards_video", author="a", text=f"comentário {i}",
                published_at=base + timedelta(hours=i), sentiment=(i % 5) + 1, intent="Elogio")
        for i in range(12)
    ])
    db_session.commit()
    return "cards_video"


def _criar_cards(db_session, youtube_id, status, analyzed_at_generation, requested_at=None):
    for kind in CARD_KINDS:
        db_session.add(VideoInsight(
            youtube_id=youtube_id, kind=kind, status=status,
            content=f"conteúdo de {kind}", analyzed_at_generation=analyzed_at_generation,
            requested_at=requested_at or datetime.utcnow(),
            generated_at=datetime.utcnow() if status == "ready" else None,
        ))
    db_session.commit()


# ------------------------------------------------------- count_analyzed

def test_count_analyzed_ignora_nao_analisados_e_erro_ia(db_session, video_com_analisados):
    from app.repositories.InsightsRepository import InsightsRepository

    db_session.add_all([
        Comment(id="sem_ia", youtube_id="cards_video", author="a", text="t",
                published_at=datetime(2026, 2, 1), sentiment=None),
        Comment(id="erro_ia", youtube_id="cards_video", author="a", text="t",
                published_at=datetime(2026, 2, 2), sentiment=3, intent="Erro_IA"),
    ])
    db_session.commit()

    assert InsightsRepository(db_session).count_analyzed("cards_video") == 12


# --------------------------------------------------- leitura e enfileiramento

def test_primeira_leitura_enfileira_geracao(db_session, video_com_analisados):
    from app.use_cases.Insights.insight_cards import get_insight_cards_use_case

    with patch("app.celery.insight_tasks.generate_video_insights") as task:
        resultado = get_insight_cards_use_case(db_session, "cards_video")

    task.delay.assert_called_once_with("cards_video")
    assert resultado["generating"] is True
    assert resultado["analyzed_now"] == 12
    assert {c.status for c in resultado["cards"]} == {"pending"}
    assert len(resultado["cards"]) == len(CARD_KINDS)


def test_poucos_analisados_nao_gera(db_session, test_user):
    from app.use_cases.Insights.insight_cards import get_insight_cards_use_case

    db_session.add(Video(youtube_id="poucos", titulo="Poucos", user_id=test_user.id))
    db_session.commit()
    db_session.add_all([
        Comment(id=f"p{i}", youtube_id="poucos", author="a", text="t",
                published_at=datetime(2026, 1, 1), sentiment=4, intent="Elogio")
        for i in range(MIN_ANALYZED_TO_GENERATE - 1)
    ])
    db_session.commit()

    with patch("app.celery.insight_tasks.generate_video_insights") as task:
        resultado = get_insight_cards_use_case(db_session, "poucos")

    task.delay.assert_not_called()
    assert resultado["generating"] is False
    assert resultado["cards"] == []


def test_cards_pending_recentes_nao_reenfileiram(db_session, video_com_analisados):
    from app.use_cases.Insights.insight_cards import get_insight_cards_use_case

    _criar_cards(db_session, "cards_video", "pending", 0)

    with patch("app.celery.insight_tasks.generate_video_insights") as task:
        resultado = get_insight_cards_use_case(db_session, "cards_video")

    task.delay.assert_not_called()
    assert resultado["generating"] is True


def test_pending_expirado_reenfileira(db_session, video_com_analisados):
    """Lock de 10 min: uma task que morreu não pode bloquear a geração para sempre."""
    from app.use_cases.Insights.insight_cards import get_insight_cards_use_case

    antigo = datetime.utcnow() - timedelta(minutes=GENERATION_LOCK_MINUTES + 5)
    _criar_cards(db_session, "cards_video", "pending", 0, requested_at=antigo)

    with patch("app.celery.insight_tasks.generate_video_insights") as task:
        resultado = get_insight_cards_use_case(db_session, "cards_video")

    task.delay.assert_called_once_with("cards_video")
    assert resultado["generating"] is True


def test_cards_atualizados_nao_regeneram(db_session, video_com_analisados):
    from app.use_cases.Insights.insight_cards import get_insight_cards_use_case

    _criar_cards(db_session, "cards_video", "ready", analyzed_at_generation=12)

    with patch("app.celery.insight_tasks.generate_video_insights") as task:
        resultado = get_insight_cards_use_case(db_session, "cards_video")

    task.delay.assert_not_called()
    assert resultado["stale"] is False
    assert resultado["generating"] is False
    assert all(c.content for c in resultado["cards"])


def test_conteudo_antigo_continua_visivel_durante_regeneracao(db_session, video_com_analisados):
    from app.use_cases.Insights.insight_cards import get_insight_cards_use_case

    _criar_cards(db_session, "cards_video", "ready", analyzed_at_generation=1)

    with patch("app.celery.insight_tasks.generate_video_insights"):
        resultado = get_insight_cards_use_case(db_session, "cards_video")

    assert resultado["stale"] is True
    assert resultado["generating"] is True
    assert all(c.content for c in resultado["cards"])


def test_force_regenera_mesmo_sem_staleness(db_session, video_com_analisados):
    from app.use_cases.Insights.insight_cards import get_insight_cards_use_case

    _criar_cards(db_session, "cards_video", "ready", analyzed_at_generation=12)

    with patch("app.celery.insight_tasks.generate_video_insights") as task:
        resultado = get_insight_cards_use_case(db_session, "cards_video", force=True)

    task.delay.assert_called_once_with("cards_video")
    assert resultado["generating"] is True


def test_force_respeita_geracao_em_curso(db_session, video_com_analisados):
    from app.use_cases.Insights.insight_cards import get_insight_cards_use_case

    _criar_cards(db_session, "cards_video", "pending", 0)

    with patch("app.celery.insight_tasks.generate_video_insights") as task:
        get_insight_cards_use_case(db_session, "cards_video", force=True)

    task.delay.assert_not_called()


# ---------------------------------------------------------------- endpoints

def test_endpoint_cards(client, auth_headers, video_com_analisados):
    with patch("app.celery.insight_tasks.generate_video_insights"):
        response = client.get("/insights/cards_video/cards", headers=auth_headers)

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["youtube_id"] == "cards_video"
    assert corpo["analyzed_now"] == 12
    assert len(corpo["cards"]) == len(CARD_KINDS)


def test_endpoint_cards_404_em_video_alheio(client, auth_headers, other_user_video):
    assert client.get("/insights/other_video_id/cards", headers=auth_headers).status_code == 404


def test_endpoint_generate_forca_geracao(client, auth_headers, db_session, video_com_analisados):
    _criar_cards(db_session, "cards_video", "ready", analyzed_at_generation=12)

    with patch("app.celery.insight_tasks.generate_video_insights") as task:
        response = client.post("/insights/cards_video/cards/generate", headers=auth_headers)

    assert response.status_code == 200
    task.delay.assert_called_once_with("cards_video")


# ------------------------------------------------------------- delete_video

def test_delete_video_apaga_cards(db_session, video_com_analisados):
    from app.use_cases.Video.delete_video import delete_video_use_case

    _criar_cards(db_session, "cards_video", "ready", analyzed_at_generation=12)
    user_id = db_session.query(Video).filter(Video.youtube_id == "cards_video").first().user_id

    resultado = delete_video_use_case(db_session, "cards_video", MagicMock(), user_id)

    assert resultado["deleted_comments"] == 12
    assert db_session.query(VideoInsight).filter(VideoInsight.youtube_id == "cards_video").count() == 0


# ------------------------------------------------------- task de geração

@pytest.fixture(scope="module")
def real_insight_tasks():
    from tests.helpers import load_real_module, make_celery_stub

    return load_real_module("real_insight_tasks", "app/celery/insight_tasks.py",
                            stubs=make_celery_stub(), package="app.celery")


@pytest.fixture
def task_db():
    """Sessão própria, com commits reais.

    A task faz commit por card e rollback em caso de erro; a fixture `db_session`
    envolve tudo numa transação externa, onde um rollback da task apagaria também
    os dados criados pelo teste. Aqui replica-se o que acontece no worker.
    """
    from app.core.security import hash_password
    from app.models.UserModel import User
    from tests.conftest import TestingSessionLocal

    session = TestingSessionLocal()
    user = User(email="task_worker@example.com", hashed_password=hash_password("x"),
                role="user", is_active=True)
    session.add(user)
    session.commit()

    session.add(Video(youtube_id="task_video", titulo="Task", user_id=user.id))
    session.commit()

    # Sentimentos 1..5 e intenções variadas para que os quatro CARD_SPECS
    # (resumo, reclamação, elogio, dúvidas) encontrem evidência.
    base = datetime(2026, 1, 1)
    session.add_all([
        Comment(id=f"t{i}", youtube_id="task_video", author="a", text=f"comentário {i}",
                published_at=base + timedelta(hours=i), sentiment=(i % 5) + 1,
                intent="Duvida" if i % 2 else "Elogio")
        for i in range(12)
    ])
    session.commit()

    yield session

    session.rollback()
    session.query(VideoInsight).filter(VideoInsight.youtube_id == "task_video").delete()
    session.query(Comment).filter(Comment.youtube_id == "task_video").delete()
    session.query(Video).filter(Video.youtube_id == "task_video").delete()
    session.query(User).filter(User.id == user.id).delete()
    session.commit()
    session.close()


def _rodar_task(real_insight_tasks, session, youtube_id="task_video"):
    with patch.object(real_insight_tasks, "SessionLocal", return_value=session), \
         patch.object(session, "close"):
        return real_insight_tasks.generate_video_insights(youtube_id)


def _cards(session, youtube_id="task_video"):
    return session.query(VideoInsight).filter(VideoInsight.youtube_id == youtube_id).all()


def test_task_gera_os_quatro_cards(real_insight_tasks, task_db):
    real_insight_tasks.llm_service.answer.reset_mock()
    real_insight_tasks.llm_service.answer.side_effect = None
    real_insight_tasks.llm_service.answer.return_value = "Resposta com evidência [1]."

    _rodar_task(real_insight_tasks, task_db)

    cards = _cards(task_db)
    assert {c.kind for c in cards} == set(CARD_KINDS)
    assert all(c.status == "ready" for c in cards)
    assert all(c.analyzed_at_generation == 12 for c in cards)
    resumo = next(c for c in cards if c.kind == "resumo")
    assert resumo.content == "Resposta com evidência [1]."
    assert resumo.evidence_ids


def test_task_nao_repete_cards_ja_prontos_no_mesmo_volume(real_insight_tasks, task_db):
    """Retry parcial: só os cards que ficaram para trás gastam LLM de novo."""
    for kind in CARD_KINDS:
        task_db.add(VideoInsight(youtube_id="task_video", kind=kind,
                                 status="error" if kind == "duvidas" else "ready",
                                 content="antigo", analyzed_at_generation=12))
    task_db.commit()

    real_insight_tasks.llm_service.answer.reset_mock()
    real_insight_tasks.llm_service.answer.side_effect = None
    real_insight_tasks.llm_service.answer.return_value = "Nova resposta [1]."

    _rodar_task(real_insight_tasks, task_db)

    assert real_insight_tasks.llm_service.answer.call_count == 1
    duvidas = next(c for c in _cards(task_db) if c.kind == "duvidas")
    assert duvidas.status == "ready"


def test_task_faz_retry_no_rate_limit_preservando_cards_anteriores(real_insight_tasks, task_db):
    from app.services.LLMService import LLMRateLimitError
    from tests.helpers import FakeRetry

    real_insight_tasks.llm_service.answer.reset_mock()
    real_insight_tasks.llm_service.answer.side_effect = [
        "Primeiro card [1].",
        LLMRateLimitError("saturado", retry_after_seconds=17),
    ]

    with pytest.raises(FakeRetry) as excinfo:
        _rodar_task(real_insight_tasks, task_db)

    assert excinfo.value.countdown == 17
    prontos = [c for c in _cards(task_db) if c.status == "ready"]
    assert len(prontos) == 1   # o card já gerado não se perde no retry


def test_task_marca_card_com_erro_e_continua(real_insight_tasks, task_db):
    real_insight_tasks.llm_service.answer.reset_mock()
    real_insight_tasks.llm_service.answer.side_effect = [
        RuntimeError("falha isolada"), "ok [1]", "ok [1]", "ok [1]",
    ]

    _rodar_task(real_insight_tasks, task_db)

    status = {c.kind: c.status for c in _cards(task_db)}
    assert status["resumo"] == "error"
    assert status["duvidas"] == "ready"


def test_card_com_erro_preserva_conteudo_anterior(real_insight_tasks, task_db):
    """O painel continua a mostrar o card antigo enquanto a regeneração falha."""
    task_db.add(VideoInsight(youtube_id="task_video", kind="resumo", status="ready",
                             content="resumo antigo", evidence_ids=["t1"],
                             analyzed_at_generation=1))
    task_db.commit()

    real_insight_tasks.llm_service.answer.reset_mock()
    real_insight_tasks.llm_service.answer.side_effect = [
        RuntimeError("falha"), "ok [1]", "ok [1]", "ok [1]",
    ]

    _rodar_task(real_insight_tasks, task_db)

    resumo = next(c for c in _cards(task_db) if c.kind == "resumo")
    assert resumo.status == "error"
    assert resumo.content == "resumo antigo"
    assert resumo.evidence_ids == ["t1"]
