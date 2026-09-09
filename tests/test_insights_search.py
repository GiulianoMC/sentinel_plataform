"""Fase 0 (search com ids/extra_where) e Fase 1 (busca híbrida)."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from tests.helpers import load_real_module, make_chromadb_stub


@pytest.fixture(scope="module")
def real_search_service_cls():
    module = load_real_module(
        "real_semantic_search_service",
        "app/services/SemanticSearchService.py",
        stubs=make_chromadb_stub(),
    )
    return module.SemanticSearchService


@pytest.fixture
def service_with_mock_collection(real_search_service_cls):
    """Instância sem __init__ (não carrega o modelo) com uma collection mockada."""
    service = object.__new__(real_search_service_cls)
    collection = MagicMock()
    collection.query.return_value = {
        "ids": [["c1", "c2"]],
        "documents": [["texto 1", "texto 2"]],
        "distances": [[0.1, 0.9]],
        "metadatas": [[{"video_id": "v1"}, {"video_id": "v1"}]],
    }
    service.get_collection = lambda name: collection
    return service, collection


# --------------------------------------------------------------- Fase 0

def test_search_devolve_id_e_filtra_por_threshold(service_with_mock_collection):
    service, _ = service_with_mock_collection
    resultados = service.search("bateria", video_id_filter="v1", threshold=0.6)

    assert [r["id"] for r in resultados] == ["c1"]   # c2 tem distância 0.9 > 0.6
    assert resultados[0]["documento"] == "texto 1"
    assert resultados[0]["distancia"] == 0.1


def test_search_sem_clausulas_nao_envia_where(service_with_mock_collection):
    service, collection = service_with_mock_collection
    service.search("bateria")
    assert "where" not in collection.query.call_args.kwargs


def test_search_uma_clausula_envia_where_simples(service_with_mock_collection):
    service, collection = service_with_mock_collection
    service.search("bateria", video_id_filter="v1")
    assert collection.query.call_args.kwargs["where"] == {"video_id": "v1"}


def test_search_duas_clausulas_combina_com_and(service_with_mock_collection):
    service, collection = service_with_mock_collection
    service.search("bateria", video_id_filter="v1", extra_where={"sentiment": {"$lte": 2}})
    assert collection.query.call_args.kwargs["where"] == {
        "$and": [{"video_id": "v1"}, {"sentiment": {"$lte": 2}}]
    }


def test_search_lista_de_videos_usa_in(service_with_mock_collection):
    service, collection = service_with_mock_collection
    service.search("bateria", video_id_filter=["v1", "v2"])
    assert collection.query.call_args.kwargs["where"] == {"video_id": {"$in": ["v1", "v2"]}}


def test_search_sem_resultados_devolve_lista_vazia(service_with_mock_collection):
    service, collection = service_with_mock_collection
    collection.query.return_value = {"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]}
    assert service.search("bateria") == []


# --------------------------------------------------------------- Fase 1

@pytest.fixture
def video_com_comentarios(db_session, test_user):
    from app.models.VideoModel import Comment, Video

    video = Video(youtube_id="hybrid_video", titulo="Hybrid", user_id=test_user.id)
    db_session.add(video)
    db_session.commit()

    base = datetime(2026, 1, 1)
    db_session.add_all([
        Comment(id="c1", youtube_id=video.youtube_id, author="ana", text="bateria ruim",
                published_at=base, sentiment=2, intent="Critica", product_mentioned="Poco X8 Pro"),
        Comment(id="c2", youtube_id=video.youtube_id, author="bia", text="camera boa",
                published_at=base + timedelta(days=1), sentiment=5, intent="Elogio"),
        Comment(id="c3", youtube_id=video.youtube_id, author="caio", text="preço justo",
                published_at=base + timedelta(days=2), sentiment=4, intent="Informacao_Preco"),
    ])
    db_session.commit()
    return video


def test_hybrid_search_preserva_ordem_do_chroma(db_session, video_com_comentarios):
    from app.use_cases.Insights.hybrid_search import hybrid_search_use_case

    search_service = MagicMock()
    search_service.search.return_value = [
        {"id": "c3", "documento": "preço justo", "distancia": 0.10, "metadados": {}},
        {"id": "c1", "documento": "bateria ruim", "distancia": 0.25, "metadados": {}},
        {"id": "c2", "documento": "camera boa", "distancia": 0.40, "metadados": {}},
    ]

    resultado = hybrid_search_use_case(db_session, search_service, "hybrid_video", "qualquer")

    assert [r["id"] for r in resultado] == ["c3", "c1", "c2"]
    assert [r["distance"] for r in resultado] == [0.10, 0.25, 0.40]
    assert resultado[1]["sentiment"] == 2
    assert resultado[1]["product_mentioned"] == "Poco X8 Pro"


def test_hybrid_search_ignora_ids_ausentes_no_postgres(db_session, video_com_comentarios):
    from app.use_cases.Insights.hybrid_search import hybrid_search_use_case

    search_service = MagicMock()
    search_service.search.return_value = [
        {"id": "fantasma", "documento": "orfao no chroma", "distancia": 0.05, "metadados": {}},
        {"id": "c2", "documento": "camera boa", "distancia": 0.30, "metadados": {}},
    ]

    resultado = hybrid_search_use_case(db_session, search_service, "hybrid_video", "qualquer")
    assert [r["id"] for r in resultado] == ["c2"]


def test_hybrid_search_query_vazia(db_session, video_com_comentarios):
    from app.use_cases.Insights.hybrid_search import hybrid_search_use_case

    with pytest.raises(ValueError):
        hybrid_search_use_case(db_session, MagicMock(), "hybrid_video", "   ")


def test_endpoint_search_devolve_campos_estruturados(client, auth_headers, video_com_comentarios):
    from tests.conftest import mock_search_service

    mock_search_service.search.return_value = [
        {"id": "c1", "documento": "bateria ruim", "distancia": 0.2, "metadados": {}},
    ]

    response = client.get("/insights/hybrid_video/search?q=bateria", headers=auth_headers)
    assert response.status_code == 200
    corpo = response.json()
    assert corpo[0]["id"] == "c1"
    assert corpo[0]["intent"] == "Critica"
    assert corpo[0]["distance"] == 0.2


def test_endpoint_search_repassa_filtros_ao_chroma(client, auth_headers, video_com_comentarios):
    from tests.conftest import mock_search_service

    client.get(
        "/insights/hybrid_video/search?q=bateria&sentiment_max=2&product=Poco%20X8%20Pro",
        headers=auth_headers,
    )
    extra_where = mock_search_service.search.call_args.kwargs["extra_where"]
    assert extra_where == {"$and": [{"sentiment": {"$lte": 2}}, {"product": "poco x8 pro"}]}


def test_endpoint_search_404_em_video_de_outro_usuario(client, auth_headers, other_user_video):
    response = client.get("/insights/other_video_id/search?q=bateria", headers=auth_headers)
    assert response.status_code == 404


def test_endpoint_search_exige_autenticacao(client, video_com_comentarios):
    assert client.get("/insights/hybrid_video/search?q=bateria").status_code == 401
