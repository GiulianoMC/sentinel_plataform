# app/celery/ai_tasks.py
from .celery_app import celery
from app.database import SessionLocal
from app.models.VideoModel import Comment
from app.services.GeminiService import GeminiService

# Instanciamos o serviço fora da task para otimizar recursos, tal como fez no SemanticSearch
gemini_service = GeminiService()

@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def process_comments_with_ai(self, comment_id: str, comment_text: str):
    """
    Task Celery exclusiva para processamento de IA (Fase 2).
    """
    print(f"--- [AI WORKER] A iniciar análise Gemini para o comentário: {comment_id} ---")
    db = SessionLocal()
    
    try:
        # 1. Faz a chamada à IA (Gemini)
        analysis = gemini_service.analyze_comment(comment_text)
        print(f"[AI WORKER] Resultado IA: Sentimento {analysis.sentiment}, Intenção {analysis.intent}")
        
        # 2. Guarda o resultado no banco de dados relacional
        comment = db.query(Comment).filter(Comment.id == comment_id).first()
        
        if comment:
            comment.sentiment = analysis.sentiment
            comment.intent = analysis.intent
            comment.product_mentioned = analysis.product_mentioned
            db.commit()
            print(f"--- [AI WORKER] Análise guardada com sucesso para {comment_id}! ---")
        else:
            print(f"[AI WORKER] AVISO: Comentário {comment_id} não encontrado na base de dados.")

        return f"IA processada para {comment_id}"

    except Exception as e:
        db.rollback()
        print(f"[AI WORKER] ERRO na análise de IA para {comment_id}: {e}")
        # Aciona o retry automático do Celery
        raise self.retry(exc=e)
    finally:
        db.close()