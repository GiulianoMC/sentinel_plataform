from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_active_user
from app.use_cases.IngestionRouter.execute_ingestion import execute_ingestion_use_case
from app.models.UserModel import User
from app.models.VideoModel import Video

router = APIRouter(
    prefix="/ingest",
    tags=["Ingestao"]
)


class NovoComentario(BaseModel):
    texto: str
    youtube_id: str  # Padronizado
    author: Optional[str] = "Manual"  # Opcional, padrao é "Manual"


@router.post("/comentario")
def ingerir_novo_comentario(
    comentario: NovoComentario,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Endpoint para receber um novo comentario manualmente.
    Requer um 'youtube_id' para associar o comentario.
    Opcionalmente pode receber um 'author'.
    """
    # Verifica se o vídeo pertence ao usuário
    video = db.query(Video).filter(Video.youtube_id == comentario.youtube_id, Video.user_id == current_user.id).first()
    if not video:
        raise HTTPException(status_code=404, detail=f"Vídeo '{comentario.youtube_id}' não encontrado ou não pertence ao usuário.")

    # Chamamos o use case com os nomes corretos
    resultado = execute_ingestion_use_case(
        comment_text=comentario.texto,
        video_id=comentario.youtube_id,
        author=comentario.author
    )

    return {
        "status": "Comentario recebido e agendado para processamento.",
        "comment_id": resultado["comment_id"],
        "associated_youtube_id": comentario.youtube_id
    }
