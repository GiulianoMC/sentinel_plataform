from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import get_current_active_user
from app.use_cases.Reprocess.execute_reprocess import execute_reprocess_use_case
from app.use_cases.Insights.backfill_chroma_metadata import backfill_chroma_metadata_use_case
from app.models.UserModel import User
from app.models.VideoModel import Video

router = APIRouter(
    prefix="/reprocess",
    tags=["Reprocessamento"]
)


@router.post("/ai")
def reprocess_ai_analysis(
    youtube_id: Optional[str] = Query(
        None, description="Restringe a um vídeo específico. Omitido = todos os vídeos do usuário."
    ),
    only_errors: bool = Query(
        True, description="True (padrão): só os comentários com intent='Erro_IA'. False: todos."
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Re-enfileira a análise de IA (Groq) para comentários já persistidos no Postgres.

    Útil para recuperar comentários que falharam na IA (ex: quota estourada,
    gravados como 'Erro_IA') depois de corrigir a chave/modelo/quota.
    As tasks respeitam o rate_limit configurado em process_comments_with_ai.
    """
    # Se youtube_id for fornecido, verifica se pertence ao usuário
    if youtube_id:
        video = db.query(Video).filter(Video.youtube_id == youtube_id, Video.user_id == current_user.id).first()
        if not video:
            raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado ou não pertence ao usuário.")
    
    return execute_reprocess_use_case(db, youtube_id=youtube_id, only_errors=only_errors, user_id=current_user.id)


@router.post("/chroma-metadata")
def reprocess_chroma_metadata(
    youtube_id: Optional[str] = Query(
        None, description="Restringe a um vídeo específico. Omitido = todos os vídeos do usuário."
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Re-envia a análise de IA já gravada no Postgres para os metadados do ChromaDB.

    Comentários indexados antes do write-back só têm 'video_id' nos metadados e
    por isso não passam nos filtros por sentimento/intenção/produto da busca
    vetorial. Este endpoint corrige esse histórico (e serve de rede de segurança
    para syncs perdidos, já que update em id inexistente é silencioso no Chroma).
    """
    if youtube_id:
        video = db.query(Video).filter(Video.youtube_id == youtube_id, Video.user_id == current_user.id).first()
        if not video:
            raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado ou não pertence ao usuário.")

    return backfill_chroma_metadata_use_case(db, youtube_id=youtube_id, user_id=current_user.id)
