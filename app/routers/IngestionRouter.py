from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

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
    Ele envia a tarefa de processamento para o Celery (via use case)
    e responde imediatamente.
    """
    try:
        logging.info(f"Recebida requisição para ingerir comentário: {comentario.texto[:20]}...")
        
        comment_id = execute_ingestion_use_case(comentario.texto)

        logging.info(f"Tarefa de ingestão enviada para a fila. ID: {comment_id}")

        return {
            "status": "Comentário recebido e agendado para processamento.",
            "comment_id": comment_id
        }
    except Exception as e:
        logging.error(f"Erro ao enviar tarefa para o Celery: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao agendar processamento: {e}")