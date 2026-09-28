"""Fase 3: retrieval, montagem de contexto e endpoint /ask (RAG com citações)."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from tests.helpers import load_real_module, make_openai_stub


# ------------------------------------------------------- Fase 0: retry-after

@pytest.fixture(scope="module")
def real_llm_module():
    return load_real_module(
        "real_llm_service", "app/services/LLMService.py", stubs={"openai": make_openai_stub()}
    )


@pytest.mark.parametrize("mensagem,esperado", [
    ("Rate limit reached. Please try again in 2m13s.", 138),   # 133 + 5 de margem
    ("Rate limit reached. Please try again in 30s.", 35),
    ("Rate limit reached. Please try again in 1.5s.", 6),
    ("Quota exceeded, no time given", 300),
])
def test_parse_retry_after(real_llm_module, mensagem, esperado):
    assert real_llm_module.LLMService._parse_retry_after(mensagem) == esperado


# ------------------------------------------------------------ build_context

class _FakeComment:
    def __init__(self, cid, text, sentiment=3, intent="Elogio", product=None):
        self.id = cid
        self.text = text
        self.author = "autor"
        self.sentiment = sentiment
        self.intent = intent
        self.product_mentioned = product


def test_build_context_trunca_comentario_longo():
    from app.use_cases.Insights.retrieval import MAX_COMMENT_CHARS, build_context

    contexto, usados = build_context([_FakeComment("c1", "a" * 1000)])
    assert len(usados) == 1
    assert "a" * MAX_COMMENT_CHARS in contexto
    assert "a" * (MAX_COMMENT_CHARS + 1) not in contexto


def test_build_context_numera_a_partir_de_um():
    from app.use_cases.Insights.retrieval import build_context

    contexto, usados = build_context([_FakeComment("c1", "um"), _FakeComment("c2", "dois")])
    assert contexto.startswith("[1] ")
    assert "\n[2] " in contexto
    assert [c.id for c in usados] == ["c1", "c2"]


def test_build_context_respeita_orcamento_global():
    from app.use_cases.Insights.retrieval import MAX_CONTEXT_CHARS, build_context

    comentarios = [_FakeComment(f"c{i}", "x" * 300) for i in range(200)]
    contexto, usados = build_context(comentarios)

    assert len(contexto) <= MAX_CONTEXT_CHARS
    assert 0 < len(usados) < 200


def test_build_context_lida_com_quebras_de_linha():
    from app.use_cases.Insights.retrieval import build_context

    contexto, _ = build_context([_FakeComment("c1", "linha um\nlinha dois")])
    assert contexto.count("\n") == 0


# ---------------------------------------------------------------- retrieve

@pytest.fixture
def video_analisado(db_session, test_user):
    """Vídeo com 10 comentários analisados espalhados pelas 5 notas."""
    from app.models.VideoModel import Comment, Video

    video = Video(youtube_id="ask_video", titulo="Ask", user_id=test_user.id)
    db_session.add(video)
    db_session.commit()

    base = datetime(2026, 1, 1)
    comentarios = []
    for i in range(10):
        comentarios.append(Comment(
            id=f"a{i}", youtube_id=video.youtube_id, author=f"user{i}",
            text=f"comentário número {i}", published_at=base + timedelta(hours=i),
            sentiment=(i % 5) + 1, intent="Duvida" if i % 2 else "Elogio",
        ))
    db_session.add_all(comentarios)
    db_session.commit()
    return video


def test_retrieve_auto_cai_para_sample_com_pouca_evidencia(db_session, video_analisado):
    from app.use_cases.Insights.retrieval import retrieve

    search_service = MagicMock()
    search_service.search.return_value = [
        {"id": "a1", "documento": "x", "distancia": 0.2, "metadados": {}},
    ]

    comentarios, distancias, estrategia = retrieve(
        db_session, search_service, "ask_video", "resumo", "auto", None
    )

    assert estrategia == "sample"
    assert distancias == {}
    assert len(comentarios) > 1


def test_retrieve_auto_usa_semantic_com_evidencia_suficiente(db_session, video_analisado):
    from app.use_cases.Insights.retrieval import retrieve

    search_service = MagicMock()
    search_service.search.return_value = [
        {"id": f"a{i}", "documento": "x", "distancia": 0.1 * i, "metadados": {}} for i in range(4)
    ]

    comentarios, distancias, estrategia = retrieve(
        db_session, search_service, "ask_video", "bateria", "auto", None
    )

    assert estrategia == "semantic"
    assert [c.id for c in comentarios] == ["a0", "a1", "a2", "a3"]
    assert distancias["a2"] == pytest.approx(0.2)


def test_retrieve_semantic_explicito_nao_cai_para_sample(db_session, video_analisado):
    from app.use_cases.Insights.retrieval import retrieve

    search_service = MagicMock()
    search_service.search.return_value = []

    comentarios, _, estrategia = retrieve(
        db_session, search_service, "ask_video", "bateria", "semantic", None
    )

    assert estrategia == "semantic"
    assert comentarios == []


def test_retrieve_sem_search_service_usa_sample(db_session, video_analisado):
    """O worker_ai não carrega o sentence-transformer: search_service é None."""
    from app.use_cases.Insights.retrieval import retrieve

    comentarios, _, estrategia = retrieve(db_session, None, "ask_video", "resumo", "auto", None)

    assert estrategia == "sample"
    assert comentarios


def test_sample_comments_respeita_filtros(db_session, video_analisado):
    from app.repositories.InsightsRepository import InsightsRepository
    from app.schemas.InsightsSchema import InsightFilters

    repo = InsightsRepository(db_session)
    amostra = repo.sample_comments("ask_video", limit=50, filters=InsightFilters(sentiment_max=2))

    assert amostra
    assert all(c.sentiment <= 2 for c in amostra)


def test_sample_comments_ignora_erro_ia(db_session, video_analisado):
    from app.models.VideoModel import Comment
    from app.repositories.InsightsRepository import InsightsRepository

    db_session.add(Comment(id="erro1", youtube_id="ask_video", author="x", text="falhou",
                           published_at=datetime(2026, 2, 1), sentiment=3, intent="Erro_IA"))
    db_session.commit()

    ids = [c.id for c in InsightsRepository(db_session).sample_comments("ask_video", limit=50)]
    assert "erro1" not in ids


# ------------------------------------------------------------- citações

@pytest.mark.parametrize("resposta,maximo,esperado", [
    ("A bateria dura pouco [1] e aquece [2].", 2, "A bateria dura pouco [1] e aquece [2]."),
    ("Muitos reclamam [7].", 2, "Muitos reclamam."),
    ("Vários apontam [1, 9] o preço.", 3, "Vários apontam [1] o preço."),
    ("Sem citações aqui.", 3, "Sem citações aqui."),
])
def test_strip_invalid_citations(resposta, maximo, esperado):
    from app.use_cases.Insights.ask_insight import strip_invalid_citations

    assert strip_invalid_citations(resposta, maximo) == esperado


# ------------------------------------------------------------- endpoint

def test_ask_sem_evidencia_nao_chama_llm(client, auth_headers, db_session, test_user):
    from app.models.VideoModel import Video
    from tests.conftest import mock_llm_service

    db_session.add(Video(youtube_id="vazio", titulo="Sem comentários", user_id=test_user.id))
    db_session.commit()

    response = client.post("/insights/vazio/ask", headers=auth_headers,
                           json={"question": "O que dizem sobre a bateria?"})

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["llm_called"] is False
    assert corpo["comments_in_context"] == 0
    assert corpo["sources"] == []
    assert "Não encontrei evidências" in corpo["answer"]
    mock_llm_service.answer.assert_not_called()


def test_ask_com_evidencia_devolve_fontes_numeradas(client, auth_headers, video_analisado):
    from tests.conftest import mock_llm_service

    mock_llm_service.answer.return_value = "Os usuários citam a bateria [1] e a câmera [2]."

    response = client.post("/insights/ask_video/ask", headers=auth_headers,
                           json={"question": "Faça um resumo", "strategy": "sample"})

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["llm_called"] is True
    assert corpo["strategy_used"] == "sample"
    assert corpo["comments_in_context"] == len(corpo["sources"])
    assert [s["index"] for s in corpo["sources"]] == list(range(1, len(corpo["sources"]) + 1))
    # strategy=sample não tem distância de similaridade
    assert all(s["distance"] is None for s in corpo["sources"])
    mock_llm_service.answer.assert_called_once()


def test_ask_rate_limit_do_llm_vira_503_com_retry_after(client, auth_headers, video_analisado):
    from app.services.LLMService import LLMRateLimitError
    from tests.conftest import mock_llm_service

    mock_llm_service.answer.side_effect = LLMRateLimitError("saturado", retry_after_seconds=42)

    response = client.post("/insights/ask_video/ask", headers=auth_headers,
                           json={"question": "Faça um resumo", "strategy": "sample"})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "42"


def test_ask_timeout_do_llm_vira_504(client, auth_headers, video_analisado):
    from app.services.LLMService import LLMTimeoutError
    from tests.conftest import mock_llm_service

    mock_llm_service.answer.side_effect = LLMTimeoutError("demorou")

    response = client.post("/insights/ask_video/ask", headers=auth_headers,
                           json={"question": "Faça um resumo", "strategy": "sample"})

    assert response.status_code == 504


def test_ask_404_em_video_de_outro_usuario(client, auth_headers, other_user_video):
    response = client.post("/insights/other_video_id/ask", headers=auth_headers,
                           json={"question": "Faça um resumo"})
    assert response.status_code == 404


def test_ask_pergunta_curta_e_rejeitada(client, auth_headers, video_analisado):
    response = client.post("/insights/ask_video/ask", headers=auth_headers, json={"question": "a"})
    assert response.status_code == 422


# ------------------------------------------------ saneamento da resposta

@pytest.mark.parametrize("bruto,esperado", [
    ("Bateria fraca 【6】【14】.", "Bateria fraca [6][14]."),
    ("Preço alto 〔3〕 e câmera ［5］.", "Preço alto [3] e câmera [5]."),
    ("Já em ASCII [2].", "Já em ASCII [2]."),
])
def test_normaliza_colchetes_de_largura_total(bruto, esperado):
    """gpt-oss-120b emite 【6】 em vez de [6]; sem normalizar, a validação não vê a citação."""
    from app.use_cases.Insights.ask_insight import sanitize_answer

    assert sanitize_answer(bruto, 20) == esperado


def test_citacao_invalida_em_colchete_largo_e_removida():
    from app.use_cases.Insights.ask_insight import sanitize_answer

    assert sanitize_answer("Muitos reclamam 【99】.", 20) == "Muitos reclamam."


@pytest.mark.parametrize("bruto,esperado", [
    ("* **Bateria fraca** – ruim", "Bateria fraca – ruim"),
    ("## Resumo\nOs usuários gostam", "Resumo\nOs usuários gostam"),
    ("- Primeiro ponto", "Primeiro ponto"),
    ("Texto __enfatizado__ aqui", "Texto enfatizado aqui"),
    ("Sem marcação nenhuma", "Sem marcação nenhuma"),
])
def test_strip_markdown(bruto, esperado):
    from app.use_cases.Insights.ask_insight import strip_markdown

    assert strip_markdown(bruto).strip() == esperado


def test_sanitize_answer_no_texto_real_do_card():
    """Trecho literal gerado no card 'Principal Reclamação' (20 fontes)."""
    from app.use_cases.Insights.ask_insight import sanitize_answer

    bruto = ("As reclamações são: * **Bateria fraca** – usuários relatam bateria péssima "
             "【6】【14】【20】 . * **Superaquecimento** – o aparelho esquenta 【3】 .")
    limpo = sanitize_answer(bruto, 20)

    assert "**" not in limpo
    assert "【" not in limpo
    assert "[6][14][20]." in limpo
    assert " ." not in limpo


def test_ask_sanitiza_a_resposta_do_llm(client, auth_headers, video_analisado):
    from tests.conftest import mock_llm_service

    mock_llm_service.answer.return_value = "* **Ponto** relevante 【1】 e outro 【99】."

    response = client.post("/insights/ask_video/ask", headers=auth_headers,
                           json={"question": "Faça um resumo", "strategy": "sample"})

    corpo = response.json()
    assert corpo["answer"] == "Ponto relevante [1] e outro."


# --------------------------------------------- resolução de evidence_ids

def test_comments_by_ids_preserva_ordem(client, auth_headers, video_analisado):
    response = client.post("/insights/ask_video/comments/by-ids", headers=auth_headers,
                           json={"ids": ["a5", "a1", "a3"]})

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == ["a5", "a1", "a3"]
    assert response.json()[0]["author"] == "user5"


def test_comments_by_ids_ignora_ids_inexistentes(client, auth_headers, video_analisado):
    response = client.post("/insights/ask_video/comments/by-ids", headers=auth_headers,
                           json={"ids": ["a1", "fantasma"]})

    assert [c["id"] for c in response.json()] == ["a1"]


def test_comments_by_ids_nao_vaza_comentario_de_outro_video(client, auth_headers, db_session,
                                                            video_analisado, other_user_video):
    """Ids de outro vídeo não podem ser lidos passando o próprio youtube_id no path."""
    from app.models.VideoModel import Comment

    db_session.add(Comment(id="alheio1", youtube_id="other_video_id", author="outro",
                           text="segredo", published_at=datetime(2026, 1, 1), sentiment=5))
    db_session.commit()

    response = client.post("/insights/ask_video/comments/by-ids", headers=auth_headers,
                           json={"ids": ["a1", "alheio1"]})

    assert [c["id"] for c in response.json()] == ["a1"]


def test_comments_by_ids_404_em_video_alheio(client, auth_headers, other_user_video):
    response = client.post("/insights/other_video_id/comments/by-ids", headers=auth_headers,
                           json={"ids": ["alheio1"]})
    assert response.status_code == 404


def test_comments_by_ids_valida_tamanho_da_lista(client, auth_headers, video_analisado):
    assert client.post("/insights/ask_video/comments/by-ids", headers=auth_headers,
                       json={"ids": []}).status_code == 422
    assert client.post("/insights/ask_video/comments/by-ids", headers=auth_headers,
                       json={"ids": [f"x{i}" for i in range(101)]}).status_code == 422
