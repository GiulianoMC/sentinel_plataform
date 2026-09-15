# app/routers/InsightsRouter.py
"""
Módulo de Insights: busca híbrida, RAG com citações, perguntas sugeridas e cards.

O router só trata HTTP/Pydantic e ownership; a regra de negócio vive nos use cases
em app/use_cases/Insights/.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.rate_limiter import limiter
from app.database import get_db
from app.dependencies import get_current_active_user, get_llm_service, get_search_service
from app.models.UserModel import User
from app.models.VideoModel import Video
from app.repositories.InsightsRepository import InsightsRepository
from app.schemas.InsightsSchema import (
    AskRequest,
    AskResponse,
    CommentDetail,
    CommentsByIdsRequest,
    HybridSearchResult,
    InsightCardsResponse,
    InsightFilters,
    SuggestedQuestionsResponse,
)
from app.services.LLMService import LLMConnectionError, LLMRateLimitError, LLMTimeoutError
from app.use_cases.Insights.ask_insight import AskScope, ask_insight_use_case
from app.use_cases.Insights.hybrid_search import hybrid_search_use_case
from app.use_cases.Insights.insight_cards import get_insight_cards_use_case
from app.use_cases.Insights.suggested_questions import suggested_questions_use_case
from app.utils.video_utils import get_owned_video

router = APIRouter(
    prefix="/insights",
    tags=["Insights"]
)


def _require_owned_video(db: Session, youtube_id: str, user_id: int) -> None:
    """404 quando o vídeo não existe ou não é do usuário (sem distinguir os casos)."""
    if get_owned_video(db, youtube_id, user_id) is None:
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")


def _require_owned_channel(db: Session, channel_id: str, user_id: int) -> List[str]:
    """Ids dos vídeos do usuário nesse canal; 404 se não houver nenhum.

    O escopo é sempre (canal, usuário): o mesmo canal pode ter vídeos registados
    por outros usuários, e esses nunca entram no contexto.
    """
    rows = db.query(Video.youtube_id).filter(
        Video.channel_id == channel_id, Video.user_id == user_id
    ).all()
    ids = [r[0] for r in rows]
    if not ids:
        raise HTTPException(status_code=404, detail=f"Canal '{channel_id}' não encontrado entre os seus vídeos.")
    return ids


def _run_ask(db, search_service, llm_service, scope, body: AskRequest) -> AskResponse:
    """Mapeia as falhas do LLM para HTTP; partilhado pelos /ask de vídeo e de canal."""
    try:
        return ask_insight_use_case(db, search_service, llm_service, scope, body)
    except LLMRateLimitError as e:
        raise HTTPException(
            status_code=503,
            detail="Serviço de IA temporariamente saturado.",
            headers={"Retry-After": str(e.retry_after_seconds)},
        )
    except LLMTimeoutError:
        raise HTTPException(status_code=504, detail="A IA demorou a responder. Tente uma pergunta mais curta.")
    except LLMConnectionError:
        raise HTTPException(status_code=503, detail="Serviço de IA indisponível.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Escopo canal: todos os vídeos do usuário num canal
# ---------------------------------------------------------------------------

@router.post("/channels/{channel_id}/ask", response_model=AskResponse)
@limiter.limit("10/minute")
def ask_channel_insight(
    request: Request,
    response: Response,
    channel_id: str,
    body: AskRequest,
    db: Session = Depends(get_db),
    search_service=Depends(get_search_service),
    llm_service=Depends(get_llm_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Pergunta em linguagem natural sobre os comentários de TODOS os vídeos do
    usuário num canal (RAG). Custa uma chamada ao LLM, como o /ask por vídeo.

    Cada fonte traz `youtube_id` e `video_title`, e a resposta nomeia o vídeo de
    onde vem a evidência. Perguntas comparativas ("qual vídeo teve a pior
    recepção?") são respondidas a partir dos agregados por vídeo do canal.
    """
    video_ids = _require_owned_channel(db, channel_id, current_user.id)
    scope = AskScope(video_ids=video_ids, channel_id=channel_id, user_id=current_user.id)
    return _run_ask(db, search_service, llm_service, scope, body)


@router.get("/channels/{channel_id}/suggested-questions", response_model=SuggestedQuestionsResponse)
def channel_suggested_questions(
    channel_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Perguntas sugeridas para o canal, derivadas dos agregados de todos os seus
    vídeos. Inclui perguntas comparativas entre vídeos quando há mais de um.
    """
    _require_owned_channel(db, channel_id, current_user.id)
    return {
        "channel_id": channel_id,
        "questions": suggested_questions_use_case(db, channel_id=channel_id, user_id=current_user.id),
    }


@router.get("/{youtube_id}/search", response_model=List[HybridSearchResult])
def hybrid_search(
    youtube_id: str,
    q: str = Query(..., min_length=1, description="Texto da busca semântica"),
    num_results: int = Query(10, ge=1, le=50),
    threshold: float = Query(0.6, gt=0, le=2, description="Distância máxima; menor = mais relevante"),
    sentiment_min: Optional[int] = Query(None, ge=1, le=5),
    sentiment_max: Optional[int] = Query(None, ge=1, le=5),
    intent: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    search_service=Depends(get_search_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Busca semântica enriquecida com os campos estruturados do PostgreSQL
    (sentimento, intenção, produto), preservando a ordem de relevância do ChromaDB.
    """
    _require_owned_video(db, youtube_id, current_user.id)

    filters = InsightFilters(
        sentiment_min=sentiment_min, sentiment_max=sentiment_max,
        intent=intent, product=product,
    )

    try:
        return hybrid_search_use_case(
            db=db,
            search_service=search_service,
            youtube_id=youtube_id,
            query=q,
            num_results=num_results,
            threshold=threshold,
            filters=filters,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{youtube_id}/comments/by-ids", response_model=List[CommentDetail])
def get_comments_by_ids(
    youtube_id: str,
    body: CommentsByIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Resolve uma lista de ids em comentários completos, na ordem pedida.

    Serve para o front exibir as evidências dos cards de insights, que guardam
    apenas `evidence_ids`. A consulta é restrita ao vídeo do path: ids de outros
    vídeos são silenciosamente ignorados, e não apenas os de outros usuários.
    """
    _require_owned_video(db, youtube_id, current_user.id)
    return InsightsRepository(db).get_comments_by_ids(body.ids, youtube_id=youtube_id)


@router.post("/{youtube_id}/ask", response_model=AskResponse)
@limiter.limit("10/minute")
def ask_insight(
    request: Request,
    response: Response,
    youtube_id: str,
    body: AskRequest,
    db: Session = Depends(get_db),
    search_service=Depends(get_search_service),
    llm_service=Depends(get_llm_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Pergunta em linguagem natural sobre os comentários do vídeo (RAG).

    A resposta cita as evidências com índices entre colchetes ([1], [2]),
    resolvíveis pela lista `sources`. Rate limit por cliente: a cota do LLM é
    partilhada com o worker de análise de comentários.
    """
    _require_owned_video(db, youtube_id, current_user.id)
    return _run_ask(db, search_service, llm_service, youtube_id, body)


@router.get("/{youtube_id}/suggested-questions", response_model=SuggestedQuestionsResponse)
def suggested_questions(
    youtube_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Perguntas sugeridas para o painel, derivadas dos agregados do vídeo.
    Determinístico e sem custo de LLM; cada sugestão já traz estratégia e filtros
    prontos para serem enviados ao /ask.
    """
    _require_owned_video(db, youtube_id, current_user.id)
    return {
        "youtube_id": youtube_id,
        "questions": suggested_questions_use_case(db, youtube_id),
    }


@router.get("/{youtube_id}/cards", response_model=InsightCardsResponse)
def get_cards(
    youtube_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Cards de insights em cache. Dispara a regeneração em background apenas
    quando entrou volume novo suficiente de comentários analisados.
    """
    _require_owned_video(db, youtube_id, current_user.id)
    return get_insight_cards_use_case(db, youtube_id)


@router.post("/{youtube_id}/cards/generate", response_model=InsightCardsResponse)
def force_generate_cards(
    youtube_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Força a regeneração dos cards ("atualizar insights"), ignorando o staleness.
    Uma geração já em curso continua a ser respeitada.
    """
    _require_owned_video(db, youtube_id, current_user.id)
    return get_insight_cards_use_case(db, youtube_id, force=True)
