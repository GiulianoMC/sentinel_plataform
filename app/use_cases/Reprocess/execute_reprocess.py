from typing import Optional, List

from sqlalchemy.orm import Session

from app.models.VideoModel import Comment, Video
from app.celery.ai_tasks import process_comments_with_ai


def execute_reprocess_use_case(
    db: Session,
    youtube_id: Optional[str] = None,
    only_errors: bool = True,
    user_id: int = None
) -> dict:
    """
    Re-enfileira a análise de IA (Groq) para comentários já persistidos.

    Por padrão, reprocessa apenas os que ficaram com `intent="Erro_IA"`
    (falha anterior na IA, ex: quota). Com `only_errors=False`, reprocessa
    todos os comentários do filtro — útil para reanalisar tudo após trocar o modelo.

    Filtra opcionalmente por `youtube_id`. Se `user_id` for fornecido e `youtube_id` não,
    filtra pelos vídeos do usuário. Não altera o banco aqui: apenas
    redispara `process_comments_with_ai`, que regrava sentiment/intent/product.
    """
    query = db.query(Comment)

    if only_errors:
        query = query.filter(Comment.intent == "Erro_IA")

    if youtube_id:
        query = query.filter(Comment.youtube_id == youtube_id)
    elif user_id:
        # Filtrar por vídeos do usuário
        user_video_ids = db.query(Video.youtube_id).filter(Video.user_id == user_id).all()
        user_video_ids = [v[0] for v in user_video_ids]
        if user_video_ids:
            query = query.filter(Comment.youtube_id.in_(user_video_ids))
        else:
            # Usuário não tem vídeos
            return {"reprocessed": 0, "youtube_id": youtube_id, "only_errors": only_errors}

    comentarios = query.all()

    for comentario in comentarios:
        process_comments_with_ai.delay(comentario.id, comentario.text)

    print(f"--- [REPROCESS] {len(comentarios)} comentários re-enfileirados para análise de IA. ---")

    return {
        "reprocessed": len(comentarios),
        "youtube_id": youtube_id,
        "only_errors": only_errors,
    }
