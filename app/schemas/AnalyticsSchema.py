# app/schemas/AnalyticsSchema.py
"""
Schemas Pydantic para as respostas da API de Analytics.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


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
