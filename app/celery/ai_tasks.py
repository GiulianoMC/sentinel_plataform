# app/celery/ai_tasks.py
from .celery_app import celery
from app.database import SessionLocal
from app.models.VideoModel import Comment
from app.services.LLMService import LLMService, LLMRateLimitError
from openai import APIConnectionError

llm_service = LLMService()


@celery.task(bind=True, max_retries=20, default_retry_delay=30, retry_backoff=False)
def process_comments_with_ai(self, comment_id: str, comment_text: str):
    print(f"--- [AI WORKER] A iniciar analise para o comentario: {comment_id} ---")
    db = SessionLocal()

    # Verificação de existência FORA do try/except genérico para evitar loop de retry
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        db.close()
        print(f"[AI WORKER] Comentario {comment_id} nao encontrado — descartando task.")
        return f"Comentario {comment_id} nao existe, task descartada."

    # Guardado antes do commit: o commit expira os atributos e forcaria novo SELECT.
    video_id = comment.youtube_id

    try:
        print(f"[AI WORKER] A enviar texto para analise LLM: {comment_text[:50]}...")
        analysis = llm_service.analyze_comment(comment_text)
        print(f"[AI WORKER] Resultado IA: Sentimento {analysis.sentiment}, Intencao {analysis.intent}")

        comment.sentiment = analysis.sentiment
        comment.intent = analysis.intent
        comment.product_mentioned = analysis.product_mentioned
        db.commit()

        # Write-back dos metadados no ChromaDB (fila ingestion, onde vive a collection).
        # Disparo por nome: tasks.py importa este modulo, o inverso criaria um ciclo.
        celery.send_task(
            "app.celery.tasks.sync_chroma_metadata",
            args=[comment_id, video_id, analysis.sentiment,
                  analysis.intent, analysis.product_mentioned],
        )

        print(f"--- [AI WORKER] Analise guardada com sucesso para {comment_id}! ---")
        return f"IA processada para {comment_id}"

    except LLMRateLimitError as e:
        print(f"[AI WORKER] Rate limit — aguardando {e.retry_after_seconds}s para retentar {comment_id}.")
        raise self.retry(exc=e, countdown=e.retry_after_seconds)

    except APIConnectionError as e:
        print(f"[AI WORKER] LLM inacessivel — retry em 30s para {comment_id}.")
        raise self.retry(exc=e, countdown=30)

    except Exception as e:
        db.rollback()
        print(f"[AI WORKER] ERRO na analise de IA para {comment_id}: {e}")
        raise self.retry(exc=e)

    finally:
        db.close()
