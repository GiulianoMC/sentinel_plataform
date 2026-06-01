# app/celery/ai_tasks.py
from .celery_app import celery
from app.database import SessionLocal
from app.models.VideoModel import Comment
from app.services.LLMService import LLMService

# Instanciamos o servico fora da task para otimizar recursos, tal como fez no SemanticSearch.
# (Antigo GeminiService — substituido por LLMService usando Groq por causa do limit: 0 do Gemini free tier.)
llm_service = LLMService()


# rate_limit é aplicado por worker (todos os processos prefork compartilham o balde de tokens),
# então limita o total de chamadas ao Gemini por minuto e evita estourar a quota do free tier.
# Ajuste conforme o limite RPM do seu modelo/plano.
@celery.task(bind=True, max_retries=3, default_retry_delay=60, retry_backoff=True, rate_limit="28/m")
def process_comments_with_ai(self, comment_id: str, comment_text: str):
    """
    Task Celery exclusiva para processamento de IA (Fase 2).
    Busca o comentario no PostgreSQL e atualiza com analise do Gemini.
    """
    print(f"--- [AI WORKER] A iniciar analise Gemini para o comentario: {comment_id} ---")
    db = SessionLocal()

    try:
        # Verifica se o comentario existe no PostgreSQL
        comment = db.query(Comment).filter(Comment.id == comment_id).first()

        if not comment:
            # Se nao encontrou, pode ser race condition - retry em 5 segundos
            print(f"[AI WORKER] Comentario {comment_id} nao encontrado. Possivel race condition. Retentando...")
            raise self.retry(countdown=5, max_retries=5)

        # Faz a chamada a IA (LLM)
        print(f"[AI WORKER] A enviar texto para analise LLM: {comment_text[:50]}...")
        analysis = llm_service.analyze_comment(comment_text)
        print(f"[AI WORKER] Resultado IA: Sentimento {analysis.sentiment}, Intencao {analysis.intent}")

        # Atualiza o comentario com os resultados da IA
        comment.sentiment = analysis.sentiment
        comment.intent = analysis.intent
        comment.product_mentioned = analysis.product_mentioned
        db.commit()

        print(f"--- [AI WORKER] Analise guardada com sucesso para {comment_id}! ---")
        return f"IA processada para {comment_id}"

    except Exception as e:
        db.rollback()
        print(f"[AI WORKER] ERRO na analise de IA para {comment_id}: {e}")
        # Aciona o retry automatico do Celery
        raise self.retry(exc=e)
    finally:
        db.close()
