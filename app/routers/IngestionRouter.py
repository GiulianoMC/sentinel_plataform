from fastapi import APIRouter
from pydantic import BaseModel

# Importamos o use case
from app.use_cases.IngestionRouter.execute_ingestion import execute_ingestion_use_case

router = APIRouter(
    prefix="/ingest",
    tags=["Ingestão"]
)

class NovoComentario(BaseModel):
    texto: str
    youtube_id: str # <-- MUDANÇA AQUI (padronizado)

@router.post("/comentario")
def ingerir_novo_comentario(comentario: NovoComentario):
    """
    Endpoint para receber um novo comentário manualmente.
    Requer um 'youtube_id' para associar o comentário.
    """
    
    # Chamamos o use case com os nomes corretos
    resultado = execute_ingestion_use_case(
        comment_text=comentario.texto,
        video_id=comentario.youtube_id # <-- MUDANÇA AQUI
    )

    return {
        "status": "Comentário recebido e agendado para processamento.",
        "comment_id": resultado["comment_id"],
        "associated_youtube_id": comentario.youtube_id
    }