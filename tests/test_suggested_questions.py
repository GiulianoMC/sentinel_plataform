"""Fase 4: perguntas sugeridas (determinísticas, sem LLM)."""

from datetime import datetime, timedelta

import pytest

from app.models.VideoModel import Comment, Video
from app.use_cases.Insights.suggested_questions import MAX_QUESTIONS, suggested_questions_use_case


def _criar_video(db_session, user, youtube_id, comentarios):
    """comentarios: lista de (sentiment, intent, product)."""
    db_session.add(Video(youtube_id=youtube_id, titulo=youtube_id, user_id=user.id))
    db_session.commit()

    base = datetime(2026, 1, 1)
    db_session.add_all([
        Comment(id=f"{youtube_id}_{i}", youtube_id=youtube_id, author="a",
                text=f"comentário {i}", published_at=base + timedelta(minutes=i),
                sentiment=s, intent=intent, product_mentioned=product)
        for i, (s, intent, product) in enumerate(comentarios)
    ])
    db_session.commit()


def test_video_sem_analise_devolve_apenas_fallback(db_session, test_user):
    _criar_video(db_session, test_user, "sem_analise", [(None, None, None)] * 3)

    perguntas = suggested_questions_use_case(db_session, "sem_analise")

    assert len(perguntas) == 1
    assert perguntas[0]["reason"] == "sem_analise"
    assert perguntas[0]["strategy"] == "sample"


def test_produto_critico_gera_filtro_de_sentimento_baixo(db_session, test_user):
    _criar_video(db_session, test_user, "critico",
                 [(1, "Critica", "Poco X8 Pro")] * 4 + [(2, "Critica", None)] * 3)

    perguntas = suggested_questions_use_case(db_session, "critico")
    produto = next(p for p in perguntas if p["reason"].startswith("produto_critico"))

    assert produto["strategy"] == "semantic"
    assert produto["filters"] == {"product": "poco x8 pro", "sentiment_max": 2}
    # o nome exibido é capitalizado, mas o filtro usa o valor normalizado
    assert "Poco X8 Pro" in produto["question"]


def test_produto_elogiado_gera_filtro_de_sentimento_alto(db_session, test_user):
    _criar_video(db_session, test_user, "elogiado", [(5, "Elogio", "Redmi Note 14")] * 4)

    perguntas = suggested_questions_use_case(db_session, "elogiado")
    produto = next(p for p in perguntas if p["reason"].startswith("produto_elogiado"))

    assert produto["filters"] == {"product": "redmi note 14", "sentiment_min": 4}


def test_produto_com_poucas_mencoes_e_ignorado(db_session, test_user):
    _criar_video(db_session, test_user, "mencao_unica",
                 [(1, "Critica", "Produto Raro")] + [(1, "Critica", None)] * 5)

    perguntas = suggested_questions_use_case(db_session, "mencao_unica")

    assert not any(p["reason"].startswith("produto_") for p in perguntas)


def test_erro_ia_nao_conta_como_intencao_dominante(db_session, test_user):
    _criar_video(db_session, test_user, "erro_dominante",
                 [(3, "Erro_IA", None)] * 10 + [(3, "Duvida", None)] * 3)

    perguntas = suggested_questions_use_case(db_session, "erro_dominante")
    razoes = [p["reason"] for p in perguntas]

    assert "duvidas_dominantes" in razoes
    assert not any("Erro_IA" in p["question"] for p in perguntas)


def test_intencao_de_compra_dominante(db_session, test_user):
    _criar_video(db_session, test_user, "compra", [(4, "Intencao_Compra", None)] * 6)

    perguntas = suggested_questions_use_case(db_session, "compra")
    intencao = next(p for p in perguntas if p["reason"] == "intencao_compra_dominante")

    assert intencao["filters"] == {"intent": "Intencao_Compra"}


@pytest.mark.parametrize("sentimentos,razao_esperada", [
    ([1, 1, 2, 2], "sentimento_baixo"),
    ([3, 3, 3, 4], "sentimento_misto"),
    ([5, 5, 4, 5], "sentimento_alto"),
])
def test_sugestao_por_sentimento_medio(db_session, test_user, sentimentos, razao_esperada):
    youtube_id = f"sent_{razao_esperada}"
    _criar_video(db_session, test_user, youtube_id, [(s, "Comparacao", None) for s in sentimentos])

    razoes = [p["reason"] for p in suggested_questions_use_case(db_session, youtube_id)]
    assert razao_esperada in razoes


def test_nunca_mais_de_cinco_perguntas(db_session, test_user):
    """Com 3 produtos críticos + intenção + sentimento + fallback a lista é cortada em 5."""
    _criar_video(db_session, test_user, "cheio",
                 [(1, "Duvida", "Produto A")] * 4
                 + [(1, "Duvida", "Produto B")] * 4
                 + [(1, "Duvida", "Produto C")] * 4)

    perguntas = suggested_questions_use_case(db_session, "cheio")

    assert len(perguntas) == MAX_QUESTIONS
    # as mais específicas (produto) têm prioridade sobre o resumo genérico
    assert sum(1 for p in perguntas if p["reason"].startswith("produto_")) == 3


def test_fallback_presente_quando_ha_espaco(db_session, test_user):
    _criar_video(db_session, test_user, "com_espaco", [(5, "Elogio", None)] * 4)

    perguntas = suggested_questions_use_case(db_session, "com_espaco")

    assert len(perguntas) < MAX_QUESTIONS
    assert perguntas[-1]["reason"] == "fallback"


def test_toda_sugestao_tem_estrategia_valida(db_session, test_user):
    _criar_video(db_session, test_user, "validade",
                 [(2, "Duvida", "Poco X8 Pro")] * 5 + [(4, "Elogio", None)] * 2)

    for pergunta in suggested_questions_use_case(db_session, "validade"):
        assert pergunta["strategy"] in ("auto", "semantic", "sample")
        assert pergunta["question"]
        assert pergunta["reason"]


def test_endpoint_suggested_questions(client, auth_headers, db_session, test_user):
    _criar_video(db_session, test_user, "endpoint_sq", [(5, "Elogio", None)] * 3)

    response = client.get("/insights/endpoint_sq/suggested-questions", headers=auth_headers)

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["youtube_id"] == "endpoint_sq"
    assert corpo["questions"]


def test_endpoint_suggested_questions_404_em_video_alheio(client, auth_headers, other_user_video):
    response = client.get("/insights/other_video_id/suggested-questions", headers=auth_headers)
    assert response.status_code == 404
