# app/celery/ai_tasks.py
import re
from .celery_app import celery
from app.database import SessionLocal
from app.models.VideoModel import Comment
from app.services.LLMService import LLMService
from groq import RateLimitError


def _retry_after_seconds(exc: RateLimitError, default: int = 300) -> int:
    """Extrai o tempo de espera da mensagem de erro do Groq (ex: 'try again in 3m56.736s')."""
    match = re.search(r'try again in (?:(\d+)m)?(\d+(?:\.\d+)?)s', str(exc))
    if match:
        minutes = int(match.group(1) or 0)
        seconds = float(match.group(2))
        return int(minutes * 60 + seconds) + 5  # +5s de margem
    return default

# Instanciamos o servico fora da task para otimizar recursos, tal como fez no SemanticSearch.
# (Antigo GeminiService — substituido por LLMService usando Groq por causa do limit: 0 do Gemini free tier.)
llm_service = LLMService()


# rate_limit por processo: 2 processos × 14/m = 28 chamadas/min total (< 30 RPM da Groq free tier).
# max_retries alto porque o TPD (100k tokens/dia) pode esgotar e precisar de várias esperas.
@celery.task(bind=True, max_retries=20, default_retry_delay=300, retry_backoff=False, rate_limit="14/m")
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

    except RateLimitError as e:
        db.close()
        countdown = _retry_after_seconds(e)
        print(f"[AI WORKER] Rate limit Groq — aguardando {countdown}s para retentar {comment_id}.")
        raise self.retry(exc=e, countdown=countdown)

    except Exception as e:
        db.rollback()
        print(f"[AI WORKER] ERRO na analise de IA para {comment_id}: {e}")
        raise self.retry(exc=e)
    finally:
        db.close()
