import uuid
from .celery_app import celery
from app.services.SemanticSearchService import SemanticSearchService

# Importamos a nova task de inteligência artificial que você criou!
from .ai_tasks import process_comments_with_ai 

COLLECTION_NAME = "comentarios_produtos"

# Instância global por worker (ótima otimização!)
semantic_service = SemanticSearchService()
collection = semantic_service.get_collection(COLLECTION_NAME)

@celery.task(bind=True)
def processar_novo_comentario(self, comment_id: str, comment_text: str, video_id: str):
    """
    Task Celery que processa e salva um comentário,
    agora incluindo o ID do vídeo e disparando a IA.
    """
    print(f"--- [WORKER] Recebi a Tarefa: Processar comentário {comment_id} para o vídeo {video_id} ---")
    try:
        print(f"[WORKER] A gerar embedding para {comment_id}...")
        embedding = semantic_service.model.encode([comment_text])

        collection.add(
            embeddings=embedding.tolist(),
            documents=[comment_text],
            ids=[comment_id],
            metadatas=[{"video_id": video_id}]
        )

        print(f"[WORKER] Embedding do comentário {comment_id} salvo no ChromaDB.")
        
        # Só disparamos o Gemini se o ChromaDB salvou com sucesso.
        print(f"[WORKER] Disparando análise de IA (Gemini) para {comment_id}...")
        process_comments_with_ai.delay(comment_id, comment_text)

        print(f"--- [WORKER] Tarefa {comment_id} concluída com sucesso! ---")
        return f"Comentário {comment_id} processado no ChromaDB e enviado para IA."

    except Exception as e:
        print(f"[WORKER] ERRO ao processar {comment_id}: {e}")
        raise self.retry(exc=e, countdown=60)