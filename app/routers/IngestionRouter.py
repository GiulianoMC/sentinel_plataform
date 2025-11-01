from fastapi import APIRouter
from pydantic import BaseModel

from app.use_cases.IngestionRouter.execute_ingestion import execute_ingestion_use_case

router = APIRouter(
    prefix="/ingest",
    tags=["Ingestão"]
)

class NovoComentario(BaseModel):
    texto: str

@router.post("/comentario")
def ingerir_novo_comentario(comentario: NovoComentario):
    """
    Endpoint para receber um novo comentário.
    Ele envia a tarefa de processamento para o Celery e responde imediatamente.
    """
    
    resultado = execute_ingestion_use_case(comentario.texto)

    return {
        "status": "Comentário recebido e agendado para processamento.",
        "comment_id": resultado["comment_id"]
    }