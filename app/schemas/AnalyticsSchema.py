# app/schemas/AnalyticsSchema.py
"""
Schemas Pydantic para as respostas da API de Analytics.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime


class VideoSummaryResponse(BaseModel):
    """Resumo geral de um vídeo (total de comentários, analisados e sentimento médio)."""
    youtube_id: str = Field(..., description="ID do vídeo no YouTube")
    total_comments: int = Field(..., description="Total de comentários no vídeo")
    analyzed_comments: int = Field(..., description="Comentários analisados pela IA (com sentiment)")
    average_sentiment: Optional[float] = Field(None, description="Média de sentimento (1-5)")

    class Config:
        from_attributes = True


class IntentData(BaseModel):
    """Dados de uma intenção específica."""
    intent: str = Field(..., description="Tipo de intenção (ex: Intencao_Compra, Duvida)")
    count: int = Field(..., description="Número de comentários com esta intenção")


class IntentionsResponse(BaseModel):
    """Resposta com a distribuição de intenções de compra."""
    youtube_id: str = Field(..., description="ID do vídeo no YouTube")
    intentions: List[IntentData] = Field(default_factory=list, description="Lista de intenções")

    class Config:
        from_attributes = True


class ProductData(BaseModel):
    """Dados de um produto mencionado."""
    product_name: str = Field(..., description="Nome do produto mencionado")
    count: int = Field(..., description="Número de menções")
    average_sentiment: float = Field(..., description="Sentimento médio associado ao produto (1-5)")


class TopProductsResponse(BaseModel):
    """Resposta com os produtos mais mencionados."""
    youtube_id: str = Field(..., description="ID do vídeo no YouTube")
    products: List[ProductData] = Field(default_factory=list, description="Lista de produtos")

    class Config:
        from_attributes = True


class SentimentDistributionResponse(BaseModel):
    """Resposta com a distribuição de sentimentos (notas 1 a 5)."""
    youtube_id: str = Field(..., description="ID do vídeo no YouTube")
    distribution: Dict[str, int] = Field(
        ...,
        description="Contagem de comentários por nota de sentimento (chaves '1' a '5')"
    )

    class Config:
        from_attributes = True


class VideoOverviewItem(BaseModel):
    """Dados de um vídeo na visão geral do usuário."""
    youtube_id: str = Field(..., description="ID do vídeo no YouTube")
    titulo: str = Field(..., description="Título do vídeo")
    created_at: datetime = Field(..., description="Data de registro do vídeo")
    total_comments: int = Field(..., description="Total de comentários no vídeo")
    analyzed_comments: int = Field(..., description="Comentários analisados pela IA (com sentiment)")
    average_sentiment: Optional[float] = Field(None, description="Média de sentimento (1-5)")

    class Config:
        from_attributes = True


class OverviewResponse(BaseModel):
    """Visão geral de todos os vídeos do usuário autenticado."""
    total_videos: int = Field(..., description="Número total de vídeos registrados")
    total_comments: int = Field(..., description="Total de comentários em todos os vídeos")
    analyzed_comments: int = Field(..., description="Comentários analisados pela IA em todos os vídeos")
    average_sentiment: Optional[float] = Field(None, description="Média geral de sentimento (1-5), ponderada por comentários analisados")
    videos: List[VideoOverviewItem] = Field(default_factory=list, description="Lista de vídeos do usuário")

    class Config:
        from_attributes = True


__all__ = [
    "VideoSummaryResponse",
    "IntentData",
    "IntentionsResponse",
    "ProductData",
    "TopProductsResponse",
    "SentimentDistributionResponse",
    "VideoOverviewItem",
    "OverviewResponse",
]
