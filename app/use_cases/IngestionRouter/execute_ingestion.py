import uuid
from app.celery.tasks import processar_novo_comentario

def execute_ingestion_use_case(comment_text: str, video_id: str) -> dict:
    """
    Use case para ingerir um novo comentário manualmente.
    Gera um ID e dispara a tarefa assíncrona com o video_id.
    """
    
    comment_id = str(uuid.uuid4())
    
    print(f"--- [API/Use Case] Recebi requisição para ingerir comentário: {comment_text[:20]}... para o vídeo {video_id} ---")

    processar_novo_comentario.delay(
        comment_id, 
        comment_text, 
        video_id 
    )

    print(f"[API/Use Case] Tarefa enviada para a fila (ID: {comment_id}). Respondendo ao cliente.")
    
    return {"comment_id": comment_id}