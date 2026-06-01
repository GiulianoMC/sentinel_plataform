from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.use_cases.Reprocess.execute_reprocess import execute_reprocess_use_case

router = APIRouter(
    prefix="/reprocess",
    tags=["Reprocessamento"]
)


@router.post("/ai")
def reprocess_ai_analysis(
    youtube_id: Optional[str] = Query(
        None, description="Restringe a um vídeo específico. Omitido = todos os vídeos."
    ),
    only_errors: bool = Query(
        True, description="True (padrão): só os comentários com intent='Erro_IA'. False: todos."
    ),
    db: Session = Depends(get_db),
):
    """
    Re-enfileira a análise de IA (Gemini) para comentários já persistidos no Postgres.

    Útil para recuperar comentários que falharam na IA (ex: quota estourada,
    gravados como 'Erro_IA') depois de corrigir a chave/modelo/quota.
    As tasks respeitam o rate_limit configurado em process_comments_with_ai.
    """
    return execute_reprocess_use_case(db, youtube_id=youtube_id, only_errors=only_errors)
