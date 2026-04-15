from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

# Importamos o use case
from app.use_cases.IngestionRouter.execute_ingestion import execute_ingestion_use_case

router = APIRouter(
    prefix="/ingest",
    tags=["Ingestao"]
)


class NovoComentario(BaseModel):
    texto: str
    youtube_id: str  # Padronizado
    author: Optional[str] = "Manual"  # Opcional, padrao é "Manual"


@router.post("/comentario")
def ingerir_novo_comentario(comentario: NovoComentario):
    """
    Endpoint para receber um novo comentario manualmente.
    Requer um 'youtube_id' para associar o comentario.
    Opcionalmente pode receber um 'author'.
    """

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
