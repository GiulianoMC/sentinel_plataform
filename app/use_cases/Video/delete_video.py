from typing import Optional
from sqlalchemy.orm import Session
from app.models.VideoModel import Video, Comment
from app.models.VideoInsightModel import VideoInsight
from app.services.SemanticSearchService import SemanticSearchService

COLLECTION_NAME = "comentarios_produtos"


def delete_video_use_case(
    db: Session,
    youtube_id: str,
    search_service: SemanticSearchService,
    user_id: int
) -> Optional[dict]:
    video = db.query(Video).filter(Video.youtube_id == youtube_id, Video.user_id == user_id).first()
    if not video:
        return None

    comment_count = db.query(Comment).filter(Comment.youtube_id == youtube_id).count()

    # Remove embeddings do ChromaDB (best-effort — não aborta se falhar)
    try:
        collection = search_service.get_collection(COLLECTION_NAME)
        collection.delete(where={"video_id": youtube_id})
    except Exception as e:
        print(f"[DELETE] Aviso: erro ao remover embeddings do ChromaDB para {youtube_id}: {e}")

    # Remove comentários, cards de insights e o vídeo do PostgreSQL.
    # Os cards são apagados explicitamente: o ondelete=CASCADE cobre o Postgres,
    # mas os testes correm em SQLite, onde a FK não é aplicada da mesma forma.
    db.query(VideoInsight).filter(VideoInsight.youtube_id == youtube_id).delete()
    db.query(Comment).filter(Comment.youtube_id == youtube_id).delete()
    db.delete(video)
    db.commit()

    return {"youtube_id": youtube_id, "deleted_comments": comment_count}
