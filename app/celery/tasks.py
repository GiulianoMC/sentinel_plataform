import time
from .celery_app import celery

from app.services.SemanticSearchService import SemanticSearchService

COLLECTION_NAME = "comentarios_produtos"

@celery.task(bind=True)
def processar_novo_comentario(self, comment_id: str, comment_text: str):
    """
    Task real do Celery para processar e salvar um novo comentário.
    """
    print(f"--- [WORKER] Recebi a Tarefa: Processar comentário {comment_id} ---")
    
    try:
        service = SemanticSearchService()
        
        print(f"[WORKER] A gerar embedding para {comment_id}...")
        embedding = service.model.encode([comment_text])
        
        collection = service.chroma_client.get_collection(name=COLLECTION_NAME)
        
        collection.add(
            embeddings=embedding.tolist(),
            documents=[comment_text],
            ids=[comment_id]
        )
        
        print(f"[WORKER] Embedding do comentário {comment_id} salvo no ChromaDB.")
        print(f"--- [WORKER] Tarefa {comment_id} concluída com sucesso! ---")
        return f"Comentário {comment_id} processado."

    except Exception as e:
        print(f"[WORKER] ERRO ao processar {comment_id}: {e}")
        raise self.retry(exc=e, countdown=60)