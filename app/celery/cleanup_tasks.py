from datetime import datetime, timezone
from .celery_app import celery
from app.database import SessionLocal
from app.models.UserModel import RevokedToken


@celery.task(name='app.celery.cleanup_tasks.cleanup_revoked_tokens')
def cleanup_revoked_tokens():
    """
    Remove expired revoked tokens from the database.
    Runs periodically to prevent the revoked_tokens table from growing indefinitely.
    """
    print(f"--- [CLEANUP] Iniciando limpeza de tokens revogados expirados... ---")
    
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        deleted = db.query(RevokedToken).filter(RevokedToken.expires_at < now).delete()
        db.commit()
        print(f"--- [CLEANUP] {deleted} tokens revogados expirados removidos. ---")
        return f"Removed {deleted} expired revoked tokens"
    except Exception as e:
        print(f"[CLEANUP] ERRO ao limpar tokens revogados: {e}")
        db.rollback()
        return "Falha na limpeza"
    finally:
        db.close()