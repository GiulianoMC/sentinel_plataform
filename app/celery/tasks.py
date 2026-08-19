import uuid
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from .celery_app import celery
from app.services.SemanticSearchService import SemanticSearchService
from app.database import SessionLocal
from app.models.VideoModel import Comment, Video

# Importamos a nova task de inteligencia artificial
from .ai_tasks import process_comments_with_ai

COLLECTION_NAME = "comentarios_produtos"

# Instancia global por worker (otima otimizacao!)
semantic_service = SemanticSearchService()
collection = semantic_service.get_collection(COLLECTION_NAME)


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def processar_novo_comentario(self, comment_id: str, comment_text: str, video_id: str,
                               author: str = "Desconhecido", published_at: str = None):
    """
    Task Celery que processa e salva um comentario:
    1. Verifica se o video existe
    2. Persiste no PostgreSQL (fonte da verdade) — idempotente (retry seguro)
    3. Indexa no ChromaDB (busca semantica) — upsert idempotente
    4. Dispara analise de IA
    """
    print(f"--- [WORKER] Recebi a Tarefa: Processar comentario {comment_id} para o video {video_id} ---")

    db = SessionLocal()
    chroma_success = False
    db_success = False

    try:
        # PASSO 0: Verificar se o video existe
        video = db.query(Video).filter(Video.youtube_id == video_id).first()
        if not video:
            print(f"[WORKER] Video {video_id} nao encontrado. Abortando.")
            return f"Video {video_id} nao encontrado."

        # PASSO 1: Persistir no PostgreSQL primeiro (fonte da verdade)
        # Idempotente: se o comentario ja foi persistido num retry anterior,
        # nao tenta inserir de novo (evita IntegrityError na PK).
        existing = db.query(Comment).filter(Comment.id == comment_id).first()
        if not existing:
            print(f"[WORKER] A persistir comentario {comment_id} no PostgreSQL...")

            if published_at is None:
                published_at = datetime.utcnow()
            elif isinstance(published_at, str):
                published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))

            comment = Comment(
                id=comment_id,
                youtube_id=video_id,
                author=author,
                text=comment_text,
                published_at=published_at
            )
            db.add(comment)
            try:
                db.commit()
            except IntegrityError:
                # Corrida entre tasks: outro worker ja persistiu o mesmo comentario
                db.rollback()
            db_success = True
            print(f"[WORKER] Comentario {comment_id} salvo no PostgreSQL com sucesso.")
        else:
            db_success = True
            print(f"[WORKER] Comentario {comment_id} ja existia no PostgreSQL. A prosseguir.")

        # PASSO 2: Indexar no ChromaDB (pode ser refeito se necessario)
        print(f"[WORKER] A gerar embedding para {comment_id}...")
        embedding = semantic_service.model.encode([comment_text])

        collection.upsert(
            embeddings=embedding.tolist(),
            documents=[comment_text],
            ids=[comment_id],
            metadatas=[{"video_id": video_id}]
        )
        chroma_success = True
        print(f"[WORKER] Embedding do comentario {comment_id} salvo no ChromaDB.")

        # PASSO 3: Disparar analise de IA apos confirmar persistencia no PostgreSQL
        print(f"[WORKER] Disparando analise de IA para {comment_id}...")
        process_comments_with_ai.delay(comment_id, comment_text)

        print(f"--- [WORKER] Tarefa {comment_id} concluida com sucesso! ---")
        return f"Comentario {comment_id} processado no ChromaDB e enviado para IA."

    except Exception as e:
        print(f"[WORKER] ERRO ao processar {comment_id}: {e}")

        # Compensacao: se ChromaDB salvou mas o PostgreSQL nao confirmou, remove do ChromaDB
        if chroma_success and not db_success:
            try:
                collection.delete(ids=[comment_id])
                print(f"[WORKER] Compensacao: Comentario {comment_id} removido do ChromaDB.")
            except Exception as cleanup_error:
                print(f"[WORKER] ERRO na compensacao: {cleanup_error}")

        db.rollback()
        raise self.retry(exc=e, countdown=60)

    finally:
        db.close()
