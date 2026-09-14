# app/schemas/AnalyticsSchema.py
"""
Schemas Pydantic para as respostas da API de Analytics.

Os endpoints por vídeo (`/analytics/{youtube_id}/...`) e por canal
(`/analytics/channels/{channel_id}/...`) devolvem o mesmo corpo, mudando só
o identificador do escopo — por isso há um par de schemas por métrica.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime


# ---------------------------------------------------------------------------
# Métricas (partilhadas entre vídeo e canal)
# ---------------------------------------------------------------------------

class SummaryMetrics(BaseModel):
    """Totais de comentários, analisados e sentimento médio."""
    total_comments: int = Field(..., description="Total de comentários")
    analyzed_comments: int = Field(..., description="Comentários analisados pela IA (com sentiment)")
    average_sentiment: Optional[float] = Field(None, description="Média de sentimento (1-5)")

    class Config:
        from_attributes = True


class IntentData(BaseModel):
    """Dados de uma intenção específica."""
    intent: str = Field(..., description="Tipo de intenção (ex: Intencao_Compra, Duvida)")
    count: int = Field(..., description="Número de comentários com esta intenção")


class ProductData(BaseModel):
    """Dados de um produto mencionado."""
    product_name: str = Field(..., description="Nome do produto mencionado")
    count: int = Field(..., description="Número de menções")
    average_sentiment: float = Field(..., description="Sentimento médio associado ao produto (1-5)")


# ---------------------------------------------------------------------------
# Por vídeo
# ---------------------------------------------------------------------------

class VideoSummaryResponse(SummaryMetrics):
    """Resumo geral de um vídeo (total de comentários, analisados e sentimento médio)."""
    youtube_id: str = Field(..., description="ID do vídeo no YouTube")


class IntentionsResponse(BaseModel):
    """Resposta com a distribuição de intenções de compra."""
    youtube_id: str = Field(..., description="ID do vídeo no YouTube")
    intentions: List[IntentData] = Field(default_factory=list, description="Lista de intenções")

    class Config:
        from_attributes = True


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


# ---------------------------------------------------------------------------
# Por canal
# ---------------------------------------------------------------------------

class ChannelSummaryResponse(SummaryMetrics):
    """Resumo agregado de todos os vídeos de um canal (do utilizador)."""
    channel_id: str = Field(..., description="ID do canal no YouTube")
    channel_title: Optional[str] = Field(None, description="Nome do canal")
    total_videos: int = Field(..., description="Vídeos do utilizador neste canal")


class ChannelIntentionsResponse(BaseModel):
    channel_id: str = Field(..., description="ID do canal no YouTube")
    intentions: List[IntentData] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ChannelTopProductsResponse(BaseModel):
    channel_id: str = Field(..., description="ID do canal no YouTube")
    products: List[ProductData] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ChannelSentimentDistributionResponse(BaseModel):
    channel_id: str = Field(..., description="ID do canal no YouTube")
    distribution: Dict[str, int] = Field(..., description="Contagem por nota ('1' a '5')")

    class Config:
        from_attributes = True


class ChannelOverviewItem(SummaryMetrics):
    """Um canal na visão por canais do utilizador."""
    channel_id: str = Field(..., description="ID do canal no YouTube")
    channel_title: Optional[str] = Field(None, description="Nome do canal")
    total_videos: int = Field(..., description="Vídeos do utilizador neste canal")


class ChannelsOverviewResponse(BaseModel):
    """Agregados por canal + quantos vídeos ainda não têm canal identificado."""
    total_channels: int = Field(..., description="Canais distintos identificados")
    videos_without_channel: int = Field(
        ..., description="Vídeos sem channel_id (registados antes do backfill). 0 = tudo identificado."
    )
    channels: List[ChannelOverviewItem] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Visão geral (dashboard inicial)
# ---------------------------------------------------------------------------

class VideoOverviewItem(SummaryMetrics):
    """Dados de um vídeo na visão geral do usuário."""
    youtube_id: str = Field(..., description="ID do vídeo no YouTube")
    titulo: str = Field(..., description="Título do vídeo")
    channel_id: Optional[str] = Field(None, description="ID do canal (None = ainda não identificado)")
    channel_title: Optional[str] = Field(None, description="Nome do canal")
    created_at: datetime = Field(..., description="Data de registro do vídeo")


class OverviewResponse(BaseModel):
    """Visão geral dos vídeos do usuário autenticado (todos ou de um canal)."""
    channel_id: Optional[str] = Field(None, description="Canal usado como filtro (None = todos os vídeos)")
    total_videos: int = Field(..., description="Número total de vídeos no escopo")
    total_comments: int = Field(..., description="Total de comentários no escopo")
    analyzed_comments: int = Field(..., description="Comentários analisados pela IA no escopo")
    average_sentiment: Optional[float] = Field(None, description="Média geral de sentimento (1-5), ponderada por comentários analisados")
    videos: List[VideoOverviewItem] = Field(default_factory=list, description="Lista de vídeos no escopo")

    class Config:
        from_attributes = True


__all__ = [
    "SummaryMetrics",
    "VideoSummaryResponse",
    "IntentData",
    "IntentionsResponse",
    "ProductData",
    "TopProductsResponse",
    "SentimentDistributionResponse",
    "ChannelSummaryResponse",
    "ChannelIntentionsResponse",
    "ChannelTopProductsResponse",
    "ChannelSentimentDistributionResponse",
    "ChannelOverviewItem",
    "ChannelsOverviewResponse",
    "VideoOverviewItem",
    "OverviewResponse",
]
