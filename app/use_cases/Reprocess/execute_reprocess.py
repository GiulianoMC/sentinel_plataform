from typing import Optional

from sqlalchemy.orm import Session

from app.models.VideoModel import Comment
from app.celery.ai_tasks import process_comments_with_ai


def execute_reprocess_use_case(
    db: Session,
    youtube_id: Optional[str] = None,
    only_errors: bool = True,
) -> dict:
    """
    Re-enfileira a análise de IA (Gemini) para comentários já persistidos.

    Por padrão, reprocessa apenas os que ficaram com `intent="Erro_IA"`
    (falha anterior na IA, ex: quota). Com `only_errors=False`, reprocessa
    todos os comentários do filtro — útil para reanalisar tudo após trocar o modelo.

    Filtra opcionalmente por `youtube_id`. Não altera o banco aqui: apenas
    redispara `process_comments_with_ai`, que regrava sentiment/intent/product.
    """
    query = db.query(Comment)

    if only_errors:
        query = query.filter(Comment.intent == "Erro_IA")

    if youtube_id:
        query = query.filter(Comment.youtube_id == youtube_id)

    comentarios = query.all()

    for comentario in comentarios:
        process_comments_with_ai.delay(comentario.id, comentario.text)

    print(f"--- [REPROCESS] {len(comentarios)} comentários re-enfileirados para análise de IA. ---")

    return {
        "reprocessed": len(comentarios),
        "youtube_id": youtube_id,
        "only_errors": only_errors,
    }
