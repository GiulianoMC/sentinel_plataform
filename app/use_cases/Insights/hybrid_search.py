# app/use_cases/Insights/hybrid_search.py
"""Busca híbrida: relevância semântica do Chroma + campos estruturados do Postgres."""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.repositories.InsightsRepository import InsightsRepository
from app.schemas.InsightsSchema import InsightFilters


def hybrid_search_use_case(
    db: Session,
    search_service,
    youtube_id: str,
    query: str,
    num_results: int = 10,
    threshold: float = 0.6,
    filters: Optional[InsightFilters] = None,
) -> List[Dict[str, Any]]:
    """Busca no Chroma e devolve os comentários completos, na ordem de relevância.

    Comentários presentes no Chroma mas ausentes do Postgres (compensação falhada)
    são simplesmente omitidos — o Postgres é a fonte da verdade.
    """
    if not query or not query.strip():
        raise ValueError("A query não pode estar vazia.")

    hits = search_service.search(
        query=query,
        video_id_filter=youtube_id,
        num_results=num_results,
        threshold=threshold,
        extra_where=filters.to_chroma_where() if filters else None,
    )
    if not hits:
        return []

    distance_by_id = {h["id"]: h["distancia"] for h in hits}
    comments = InsightsRepository(db).get_comments_by_ids([h["id"] for h in hits])

    return [
        {
            "id": c.id,
            "text": c.text,
            "author": c.author,
            "published_at": c.published_at,
            "sentiment": c.sentiment,
            "intent": c.intent,
            "product_mentioned": c.product_mentioned,
            "distance": distance_by_id[c.id],
        }
        for c in comments
    ]
