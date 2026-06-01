from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.AnalyticsRepository import AnalyticsRepository
from app.schemas.AnalyticsSchema import (
    VideoSummaryResponse,
    IntentionsResponse,
    TopProductsResponse,
    SentimentDistributionResponse,
)

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"]
)


@router.get("/{youtube_id}/summary", response_model=VideoSummaryResponse)
def get_video_summary(youtube_id: str, db: Session = Depends(get_db)):
    """
    Resumo do vídeo: total de comentários, quantos foram analisados pela IA
    e o sentimento médio. Usado pelo front-end como visão geral.
    """
    repo = AnalyticsRepository(db)
    resultado = repo.get_video_summary(youtube_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")
    return resultado


@router.get("/{youtube_id}/intentions", response_model=IntentionsResponse)
def get_intentions_distribution(youtube_id: str, db: Session = Depends(get_db)):
    """
    Distribuição de intenções dos comentários (ex: Intencao_Compra, Duvida),
    ordenada da mais frequente para a menos frequente.
    """
    repo = AnalyticsRepository(db)
    resultado = repo.get_intentions_distribution(youtube_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")
    return resultado


@router.get("/{youtube_id}/products", response_model=TopProductsResponse)
def get_top_products(
    youtube_id: str,
    limit: int = Query(5, ge=1, le=100, description="Número máximo de produtos a retornar"),
    min_mentions: int = Query(1, ge=1, description="Número mínimo de menções para incluir"),
    db: Session = Depends(get_db),
):
    """
    Produtos mais mencionados nos comentários, com contagem de menções
    e sentimento médio associado a cada produto.
    """
    repo = AnalyticsRepository(db)
    resultado = repo.get_top_products(youtube_id, limit=limit, min_mentions=min_mentions)
    if resultado is None:
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")
    return resultado


@router.get("/{youtube_id}/sentiment", response_model=SentimentDistributionResponse)
def get_sentiment_distribution(youtube_id: str, db: Session = Depends(get_db)):
    """
    Distribuição de sentimentos (notas 1 a 5) dos comentários do vídeo.
    Todas as notas são sempre retornadas, mesmo que com contagem zero.
    """
    repo = AnalyticsRepository(db)
    resultado = repo.get_sentiment_distribution(youtube_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")
    return resultado
