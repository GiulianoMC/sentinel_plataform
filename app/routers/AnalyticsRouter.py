from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_active_user
from app.repositories.AnalyticsRepository import AnalyticsRepository
from app.schemas.AnalyticsSchema import (
    VideoSummaryResponse,
    IntentionsResponse,
    TopProductsResponse,
    SentimentDistributionResponse,
    OverviewResponse,
)
from app.models.UserModel import User

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"]
)


def _check_video_ownership(db: Session, youtube_id: str, user_id: int) -> bool:
    """Verifica se o vídeo pertence ao utilizador."""
    from app.models.VideoModel import Video
    video = db.query(Video).filter(Video.youtube_id == youtube_id, Video.user_id == user_id).first()
    return video is not None


@router.get("/overview", response_model=OverviewResponse)
def get_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Visão geral de todos os vídeos do usuário autenticado: totais agregados
    (vídeos, comentários, analisados, sentimento médio) e dados por vídeo.
    Substitui as N chamadas a /{youtube_id}/summary no dashboard.
    """
    repo = AnalyticsRepository(db)
    return repo.get_overview(current_user.id)


@router.get("/{youtube_id}/summary", response_model=VideoSummaryResponse)
def get_video_summary(
    youtube_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Resumo do vídeo: total de comentários, quantos foram analisados pela IA
    e o sentimento médio. Usado pelo front-end como visão geral.
    """
    if not _check_video_ownership(db, youtube_id, current_user.id):
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")
    
    repo = AnalyticsRepository(db)
    resultado = repo.get_video_summary(youtube_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")
    return resultado


@router.get("/{youtube_id}/intentions", response_model=IntentionsResponse)
def get_intentions_distribution(
    youtube_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Distribuição de intenções dos comentários (ex: Intencao_Compra, Duvida),
    ordenada da mais frequente para a menos frequente.
    """
    if not _check_video_ownership(db, youtube_id, current_user.id):
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")
    
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
    current_user: User = Depends(get_current_active_user)
):
    """
    Produtos mais mencionados nos comentários, com contagem de menções
    e sentimento médio associado a cada produto.
    """
    if not _check_video_ownership(db, youtube_id, current_user.id):
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")
    
    repo = AnalyticsRepository(db)
    resultado = repo.get_top_products(youtube_id, limit=limit, min_mentions=min_mentions)
    if resultado is None:
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")
    return resultado


@router.get("/{youtube_id}/sentiment", response_model=SentimentDistributionResponse)
def get_sentiment_distribution(
    youtube_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Distribuição de sentimentos (notas 1 a 5) dos comentários do vídeo.
    Todas as notas são sempre retornadas, mesmo que com contagem zero.
    """
    if not _check_video_ownership(db, youtube_id, current_user.id):
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")
    
    repo = AnalyticsRepository(db)
    resultado = repo.get_sentiment_distribution(youtube_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")
    return resultado
