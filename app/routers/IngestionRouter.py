from fastapi import APIRouter
from pydantic import BaseModel

from app.use_cases.IngestionRouter.execute_ingestion import execute_ingestion_use_case

router = APIRouter(
    prefix="/ingest",
    tags=["Ingestão"]
)

class NovoComentario(BaseModel):
    texto: str
    video_id: str

@router.post("/comentario")
def ingerir_novo_comentario(comentario: NovoComentario):
    """
    Endpoint para receber um novo comentário manualmente.
    Agora requer um 'video_id' para associar o comentário.
    """
    
    resultado = execute_ingestion_use_case(
        comment_text=comentario.texto,
        video_id=comentario.video_id 
    )

    return {
        "status": "Comentário recebido e agendado para processamento.",
        "comment_id": resultado["comment_id"],
        "associated_video_id": comentario.video_id
    }