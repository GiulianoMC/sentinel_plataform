# app/use_cases/Insights/backfill_chroma_metadata.py
"""
Backfill dos metadados de IA no ChromaDB.

Comentários indexados antes do write-back (ou cujo `update` caiu em id
inexistente) só têm {"video_id"} nos metadados e não passam nos filtros por
sentimento/intenção/produto. Este use case re-enfileira o sync para eles.
"""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.VideoModel import Comment, Video

BATCH_SIZE = 500


def backfill_chroma_metadata_use_case(
    db: Session,
    youtube_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> dict:
    """Enfileira sync_chroma_metadata para cada comentário já analisado.

    O disparo é por nome (send_task) para não importar app.celery.tasks aqui —
    esse módulo instancia o sentence-transformer no import.
    """
    from app.celery.celery_app import celery

    query = db.query(Comment).filter(Comment.sentiment.isnot(None))

    if youtube_id:
        query = query.filter(Comment.youtube_id == youtube_id)
    elif user_id is not None:
        user_video_ids: List[str] = [
            v[0] for v in db.query(Video.youtube_id).filter(Video.user_id == user_id).all()
        ]
        if not user_video_ids:
            return {"enqueued": 0, "youtube_id": youtube_id}
        query = query.filter(Comment.youtube_id.in_(user_video_ids))

    enqueued = 0
    for comment in query.yield_per(BATCH_SIZE):
        celery.send_task(
            "app.celery.tasks.sync_chroma_metadata",
            args=[
                comment.id,
                comment.youtube_id,
                comment.sentiment,
                comment.intent,
                comment.product_mentioned,
            ],
        )
        enqueued += 1

    print(f"--- [BACKFILL] {enqueued} comentários re-enfileirados para sync de metadados. ---")
    return {"enqueued": enqueued, "youtube_id": youtube_id}
