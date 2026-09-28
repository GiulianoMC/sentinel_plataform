import uuid
from datetime import datetime
# Importamos a task real do Celery
from app.celery.tasks import processar_novo_comentario


def execute_ingestion_use_case(comment_text: str, video_id: str, author: str = "Manual") -> dict:
    """
    Use case para ingerir um novo comentario manualmente.
    Gera um ID e dispara a tarefa assincrona com o video_id.
    """

    comment_id = str(uuid.uuid4())
    published_at = datetime.utcnow().isoformat()

    print(f"--- [API/Use Case] Recebi requisicao para ingerir comentario: {comment_text[:20]}... para o video {video_id} ---")

    # Dispara a tarefa para o worker Celery com todos os metadados
    processar_novo_comentario.delay(
        comment_id=comment_id,
        comment_text=comment_text,
        video_id=video_id,
        author=author,
        published_at=published_at
    )

    print(f"[API/Use Case] Tarefa enviada para a fila (ID: {comment_id}). Respondendo ao cliente.")

    return {"comment_id": comment_id}
