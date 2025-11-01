import uuid
import logging
from app.celery.tasks import processar_novo_comentario

def execute_ingestion_use_case(texto: str) -> str:
    """
    Lógica de negócio para ingerir um novo comentário.
    1. Gera um ID.
    2. Dispara a tarefa assíncrona do Celery.
    3. Retorna o ID.
    """
    
    comment_id = str(uuid.uuid4())
    
    try:
        processar_novo_comentario.delay(comment_id, texto)
    except Exception as e:
        logging.error(f"Falha ao conectar no RabbitMQ/Celery: {e}")
        raise 
    return comment_id