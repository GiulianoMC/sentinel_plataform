"""RAG por canal: retrieval em lista de vídeos, amostra distribuída, rótulos no prompt,
fontes com título do vídeo e os endpoints /insights/channels/{channel_id}/*."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.VideoModel import Comment, Video

TITULOS = {"a1": "Review Poco X8", "a2": "Unboxing Galaxy A55", "a3": "Top 5 fones"}


@pytest.fixture
def canal(db_session, test_user, other_user):
    """Canal UC_A com 3 vídeos do test_user (6, 4 e 3 comentários analisados) e um vídeo
    do other_user no mesmo canal, que nunca pode entrar no contexto."""
    db_session.add_all([
        Video(youtube_id="a1", titulo=TITULOS["a1"], channel_id="UC_A", channel_title="Canal A", user_id=test_user.id),
        Video(youtube_id="a2", titulo=TITULOS["a2"], channel_id="UC_A", channel_title="Canal A", user_id=test_user.id),
        Video(youtube_id="a3", titulo=TITULOS["a3"], channel_id="UC_A", channel_title="Canal A", user_id=test_user.id),
        Video(youtube_id="o1", titulo="Alheio", channel_id="UC_A", channel_title="Canal A", user_id=other_user.id),
    ])
    db_session.commit()

    base = datetime(2026, 1, 1)
    comentarios = []
    for vid, n in (("a1", 6), ("a2", 4), ("a3", 3)):
        for i in range(n):
            comentarios.append(Comment(
                id=f"{vid}c{i}", youtube_id=vid, author=f"user{i}",
                text=f"comentário {i} do {TITULOS[vid]}", published_at=base + timedelta(hours=i),
                sentiment=(i % 5) + 1, intent="Duvida" if i % 2 else "Elogio",
                product_mentioned="Produto X" if i % 3 == 0 else None,
            ))
    comentarios.append(Comment(
        id="o1c0", youtube_id="o1", author="x", text="do outro usuário",
        published_at=base, sentiment=1, intent="Critica",
    ))
    db_session.add_all(comentarios)
    db_session.commit()


# ----------------------------------------------------------------- retrieval

def test_retrieve_passa_lista_de_videos_ao_search(db_session, canal):
    from app.use_cases.Insights.retrieval import retrieve

    search_service = MagicMock()
    search_service.search.return_value = [
        {"id": "a1c0", "documento": "x", "distancia": 0.1, "metadados": {}},
        {"id": "a2c0", "documento": "x", "distancia": 0.2, "metadados": {}},
    ]
    comentarios, _, estrategia = retrieve(
        db_session, search_service, ["a1", "a2", "a3"], "bateria", "semantic", None
    )
    assert estrategia == "semantic"
    assert search_service.search.call_args.kwargs["video_id_filter"] == ["a1", "a2", "a3"]
    assert [c.youtube_id for c in comentarios] == ["a1", "a2"]


def test_retrieve_um_video_mantem_filtro_string(db_session, canal):
    from app.use_cases.Insights.retrieval import retrieve

    search_service = MagicMock()
    search_service.search.return_value = []
    retrieve(db_session, search_service, ["a1"], "bateria", "semantic", None)
    assert search_service.search.call_args.kwargs["video_id_filter"] == "a1"


def test_sample_comments_cobre_todos_os_videos_e_ignora_alheios(db_session, canal):
    from app.repositories.InsightsRepository import InsightsRepository

    amostra = InsightsRepository(db_session).sample_comments(["a1", "a2", "a3"], limit=50)
    videos = {c.youtube_id for c in amostra}
    assert videos == {"a1", "a2", "a3"}
    assert all(c.youtube_id != "o1" for c in amostra)


def test_sample_comments_com_limite_pequeno_distribui_entre_videos(db_session, canal):
    """Sem o round-robin, limit=6 devolveria só os 6 mais recentes (todos do mesmo vídeo)."""
    from app.repositories.InsightsRepository import InsightsRepository

    amostra = InsightsRepository(db_session).sample_comments(["a1", "a2", "a3"], limit=6)
    assert len(amostra) <= 6
    assert len({c.youtube_id for c in amostra}) >= 2


def test_sample_comments_aceita_string_como_antes(db_session, canal):
    from app.repositories.InsightsRepository import InsightsRepository

    amostra = InsightsRepository(db_session).sample_comments("a1", limit=50)
    assert amostra and {c.youtube_id for c in amostra} == {"a1"}


def test_build_context_prefixa_video_so_quando_ha_rotulos(db_session, canal):
    from app.use_cases.Insights.retrieval import build_context

    comentarios = db_session.query(Comment).filter(Comment.youtube_id.in_(["a1", "a2"])).all()

    com_rotulos, _ = build_context(comentarios, {"a1": "V1", "a2": "V2"})
    assert "(vídeo=V1, sentimento=" in com_rotulos
    assert "(vídeo=V2, sentimento=" in com_rotulos

    sem_rotulos, _ = build_context(comentarios)
    assert "vídeo=" not in sem_rotulos
    assert sem_rotulos.startswith("[1] (sentimento=")


# ------------------------------------------------------------- /channels ask

def _prompt_enviado(mock_llm):
    return mock_llm.answer.call_args.args[0]


def test_ask_canal_devolve_fontes_com_video_e_prompt_com_legenda(client, auth_headers, canal):
    from tests.conftest import mock_llm_service

    mock_llm_service.answer.return_value = "No Review Poco X8 reclamam da bateria [1]."

    response = client.post(
        "/insights/channels/UC_A/ask", headers=auth_headers,
        json={"question": "Faça um resumo geral", "strategy": "sample"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["llm_called"] is True
    assert data["strategy_used"] == "sample"
    assert data["sources"]
    assert {s["youtube_id"] for s in data["sources"]} <= {"a1", "a2", "a3"}
    assert all(s["video_title"] == TITULOS[s["youtube_id"]] for s in data["sources"])

    prompt = _prompt_enviado(mock_llm_service)
    # Rótulo V1 é o vídeo mais comentado (a1), e a legenda liga rótulo ao título
    assert 'V1: "Review Poco X8"' in prompt
    assert "Vídeos do canal" in prompt
    assert "(vídeo=V" in prompt
    assert "Canal: Canal A | vídeos: 3" in prompt
    assert "VÁRIOS vídeos de um canal" in prompt
    mock_llm_service.answer.assert_called_once()


def test_ask_canal_nao_inclui_comentarios_de_outro_usuario(client, auth_headers, canal):
    from tests.conftest import mock_llm_service

    mock_llm_service.answer.return_value = "ok [1]"
    response = client.post(
        "/insights/channels/UC_A/ask", headers=auth_headers,
        json={"question": "resumo", "strategy": "sample"},
    )
    assert response.status_code == 200
    assert all(s["id"] != "o1c0" for s in response.json()["sources"])
    assert "do outro usuário" not in _prompt_enviado(mock_llm_service)


def test_ask_canal_semantic_filtra_pelos_videos_do_usuario(client, auth_headers, canal):
    from tests.conftest import mock_llm_service, mock_search_service

    mock_search_service.search.return_value = [
        {"id": "a2c1", "documento": "x", "distancia": 0.1, "metadados": {}},
        {"id": "a3c0", "documento": "x", "distancia": 0.2, "metadados": {}},
        {"id": "a1c2", "documento": "x", "distancia": 0.3, "metadados": {}},
    ]
    mock_llm_service.answer.return_value = "resposta [1]"

    response = client.post(
        "/insights/channels/UC_A/ask", headers=auth_headers,
        json={"question": "a bateria dura pouco?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["strategy_used"] == "semantic"
    assert [s["id"] for s in data["sources"]] == ["a2c1", "a3c0", "a1c2"]
    assert mock_search_service.search.call_args.kwargs["video_id_filter"] == ["a1", "a2", "a3"]


def test_ask_canal_sem_evidencia_nao_chama_llm(client, auth_headers, db_session, test_user):
    from tests.conftest import mock_llm_service

    db_session.add(Video(youtube_id="vazio1", titulo="Vazio", channel_id="UC_VAZIO", user_id=test_user.id))
    db_session.commit()

    response = client.post(
        "/insights/channels/UC_VAZIO/ask", headers=auth_headers,
        json={"question": "resumo geral", "strategy": "sample"},
    )
    assert response.status_code == 200
    assert response.json()["llm_called"] is False
    mock_llm_service.answer.assert_not_called()


def test_ask_canal_404_para_canal_alheio_ou_inexistente(client, auth_headers, db_session, other_user):
    db_session.add(Video(youtube_id="o9", titulo="O", channel_id="UC_ONLY_OTHER", user_id=other_user.id))
    db_session.commit()
    for canal_id in ("UC_ONLY_OTHER", "UC_NOPE"):
        response = client.post(
            f"/insights/channels/{canal_id}/ask", headers=auth_headers, json={"question": "resumo"}
        )
        assert response.status_code == 404


def test_ask_canal_401_sem_token(client, canal):
    assert client.post("/insights/channels/UC_A/ask", json={"question": "resumo"}).status_code == 401


def test_ask_canal_rate_limit_do_llm_vira_503(client, auth_headers, canal):
    from app.services.LLMService import LLMRateLimitError
    from tests.conftest import mock_llm_service

    mock_llm_service.answer.side_effect = LLMRateLimitError("saturado", retry_after_seconds=42)
    response = client.post(
        "/insights/channels/UC_A/ask", headers=auth_headers,
        json={"question": "resumo", "strategy": "sample"},
    )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "42"


# --------------------------------------------------------- /ask por vídeo (regressão)

def test_ask_video_tambem_traz_titulo_mas_sem_rotulos(client, auth_headers, canal):
    from tests.conftest import mock_llm_service

    mock_llm_service.answer.return_value = "resposta [1]"
    response = client.post(
        "/insights/a1/ask", headers=auth_headers, json={"question": "resumo", "strategy": "sample"}
    )
    assert response.status_code == 200
    data = response.json()
    assert all(s["youtube_id"] == "a1" and s["video_title"] == TITULOS["a1"] for s in data["sources"])

    prompt = _prompt_enviado(mock_llm_service)
    assert "vídeo=V" not in prompt
    assert "VÁRIOS vídeos" not in prompt


# --------------------------------------------------------- suggested questions

def test_suggested_questions_do_canal(client, auth_headers, canal):
    response = client.get("/insights/channels/UC_A/suggested-questions", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] == "UC_A"
    assert data["youtube_id"] is None

    perguntas = data["questions"]
    razoes = [p["reason"] for p in perguntas]
    assert "canal_comparar_videos" in razoes
    assert "canal_produtos_transversais" in razoes
    assert all("deste vídeo" not in p["question"] for p in perguntas)
    assert perguntas[-1]["question"].endswith("deste canal")
    assert len(perguntas) <= 5


def test_suggested_questions_canal_com_um_video_nao_compara(client, auth_headers, db_session, test_user):
    db_session.add(Video(youtube_id="solo", titulo="Solo", channel_id="UC_SOLO", user_id=test_user.id))
    db_session.commit()
    db_session.add_all([
        Comment(id=f"s{i}", youtube_id="solo", author="a", text="t", published_at=datetime(2026, 1, 1),
                sentiment=4, intent="Elogio")
        for i in range(3)
    ])
    db_session.commit()

    data = client.get("/insights/channels/UC_SOLO/suggested-questions", headers=auth_headers).json()
    assert "canal_comparar_videos" not in [p["reason"] for p in data["questions"]]


def test_suggested_questions_canal_sem_analise_devolve_fallback(client, auth_headers, db_session, test_user):
    db_session.add(Video(youtube_id="cru", titulo="Cru", channel_id="UC_CRU", user_id=test_user.id))
    db_session.commit()
    data = client.get("/insights/channels/UC_CRU/suggested-questions", headers=auth_headers).json()
    assert data["questions"] == [{
        "question": "Faça um resumo geral dos comentários deste canal",
        "reason": "sem_analise", "strategy": "sample", "filters": None,
    }]


def test_suggested_questions_canal_404_e_401(client, auth_headers, canal):
    assert client.get("/insights/channels/UC_NOPE/suggested-questions", headers=auth_headers).status_code == 404
    assert client.get("/insights/channels/UC_A/suggested-questions").status_code == 401


def test_suggested_questions_video_continua_com_youtube_id(client, auth_headers, canal):
    data = client.get("/insights/a1/suggested-questions", headers=auth_headers).json()
    assert data["youtube_id"] == "a1"
    assert data["channel_id"] is None
    assert data["questions"][-1]["question"].endswith("deste vídeo")
