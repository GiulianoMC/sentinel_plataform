# app/schemas/InsightsSchema.py
"""
Schemas Pydantic do Módulo de Insights: busca híbrida, RAG com citações,
perguntas sugeridas e cards em cache.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from typing_extensions import Literal


class InsightFilters(BaseModel):
    """Filtros estruturados aplicáveis tanto ao Chroma (where) quanto ao Postgres."""
    sentiment_min: Optional[int] = Field(None, ge=1, le=5, description="Sentimento mínimo (1-5)")
    sentiment_max: Optional[int] = Field(None, ge=1, le=5, description="Sentimento máximo (1-5)")
    intent: Optional[str] = Field(None, description="Intenção exata (ex: Duvida)")
    product: Optional[str] = Field(None, description="Produto mencionado (case-insensitive)")

    def to_chroma_where(self) -> Optional[Dict[str, Any]]:
        """Converte os filtros para a sintaxe de metadados do ChromaDB.

        Depende do write-back de metadados (sync_chroma_metadata): comentários
        indexados antes disso só têm 'video_id' e não passam nestes filtros.
        """
        clauses: List[Dict[str, Any]] = []
        if self.sentiment_min is not None:
            clauses.append({"sentiment": {"$gte": self.sentiment_min}})
        if self.sentiment_max is not None:
            clauses.append({"sentiment": {"$lte": self.sentiment_max}})
        if self.intent:
            clauses.append({"intent": self.intent})
        if self.product:
            clauses.append({"product": self.product.lower().strip()})

        if not clauses:
            return None
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}


class CommentDetail(BaseModel):
    """Comentário com os campos estruturados escritos pela IA."""
    id: str = Field(..., description="ID do comentário no YouTube (PK no Postgres e no Chroma)")
    text: str
    author: str
    published_at: datetime
    sentiment: Optional[int] = None
    intent: Optional[str] = None
    product_mentioned: Optional[str] = None

    class Config:
        from_attributes = True


class HybridSearchResult(CommentDetail):
    """Comentário devolvido pela busca híbrida (Chroma + Postgres)."""
    distance: float = Field(..., description="Distância de cosseno; menor = mais relevante")


class CommentsByIdsRequest(BaseModel):
    """Resolução de ids em comentários — usada pelos `evidence_ids` dos cards."""
    ids: List[str] = Field(..., min_length=1, max_length=100)


class AskRequest(BaseModel):
    """Pergunta em linguagem natural sobre os comentários de um vídeo."""
    question: str = Field(..., min_length=3, max_length=500)
    strategy: Literal["auto", "semantic", "sample"] = "auto"
    filters: Optional[InsightFilters] = None


class SourceComment(BaseModel):
    """Comentário que foi ao prompt; `index` é o [i] citado na resposta."""
    index: int
    id: str
    author: str
    text: str
    sentiment: Optional[int] = None
    intent: Optional[str] = None
    product_mentioned: Optional[str] = None
    distance: Optional[float] = Field(None, description="None quando a estratégia foi 'sample'")


class AskResponse(BaseModel):
    answer: str
    sources: List[SourceComment] = Field(default_factory=list)
    strategy_used: Literal["semantic", "sample"]
    comments_in_context: int
    llm_called: bool = Field(..., description="False quando não houve evidência e o LLM foi pulado")


class SuggestedQuestion(BaseModel):
    """Pergunta pronta para ser enviada ao /ask, já com estratégia e filtros."""
    question: str
    reason: str = Field(..., description="Por que a pergunta foi sugerida (para telemetria/debug)")
    strategy: Literal["auto", "semantic", "sample"]
    filters: Optional[InsightFilters] = None


class SuggestedQuestionsResponse(BaseModel):
    youtube_id: str
    questions: List[SuggestedQuestion] = Field(default_factory=list)


class InsightCard(BaseModel):
    """Card de insight pré-gerado e guardado no Postgres."""
    kind: str = Field(..., description="resumo | reclamacao_principal | elogio_principal | duvidas")
    status: str = Field(..., description="pending | ready | error")
    content: Optional[str] = None
    evidence_ids: Optional[List[str]] = None
    generated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InsightCardsResponse(BaseModel):
    youtube_id: str
    cards: List[InsightCard] = Field(default_factory=list)
    stale: bool = Field(..., description="Há comentários analisados suficientes para regenerar")
    generating: bool = Field(..., description="Uma geração está em curso")
    analyzed_now: int = Field(..., description="Comentários analisados no momento da leitura")


__all__ = [
    "InsightFilters",
    "CommentDetail",
    "HybridSearchResult",
    "CommentsByIdsRequest",
    "AskRequest",
    "SourceComment",
    "AskResponse",
    "SuggestedQuestion",
    "SuggestedQuestionsResponse",
    "InsightCard",
    "InsightCardsResponse",
]
