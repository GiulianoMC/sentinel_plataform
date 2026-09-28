from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_search_service, get_current_active_user
from app.services.SemanticSearchService import SemanticSearchService
from typing import Optional, List
from datetime import datetime

from app.use_cases.Video.register_video import register_video_use_case
from app.use_cases.Video.list_videos import list_videos_use_case
from app.use_cases.Video.list_channels import list_channels_use_case
from app.use_cases.Video.delete_video import delete_video_use_case
from app.models.UserModel import User

router = APIRouter(
    prefix="/video",
    tags=["Vídeos"]
)

class VideoRegisterRequest(BaseModel):
    video_url: str
    titulo: Optional[str] = None

class VideoResponse(BaseModel):
    id: int
    youtube_id: str
    titulo: Optional[str]
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    ultimo_comentario_verificado_em: Optional[datetime]

    class Config:
        from_attributes = True


class ChannelResponse(BaseModel):
    channel_id: str
    channel_title: Optional[str] = None
    video_count: int


@router.post("/register", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
def register_video(
    request: VideoRegisterRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Endpoint para registar um novo vídeo do YouTube
    a partir de um URL para ser monitorizado.
    """
    try:
        video_registado = register_video_use_case(
            db=db, 
            video_url=request.video_url,
            titulo=request.titulo,
            user_id=current_user.id
        )
        return video_registado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[VIDEO] Erro inesperado ao registar vídeo: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao registar o vídeo")

@router.get("/list", response_model=List[VideoResponse])
def list_videos(
    channel_id: Optional[str] = Query(
        None, description="Restringe aos vídeos deste canal (YouTube channelId). Omitido = todos."
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Endpoint para listar os vídeos do usuário autenticado, opcionalmente
    filtrados por canal.
    """
    try:
        videos = list_videos_use_case(db=db, user_id=current_user.id, channel_id=channel_id)
        return videos
    except Exception as e:
        print(f"[VIDEO] Erro inesperado ao listar vídeos: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao listar vídeos")


@router.get("/channels", response_model=List[ChannelResponse])
def list_channels(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Canais distintos dos vídeos do usuário, com contagem de vídeos.
    Alimenta o filtro por canal no front-end. Vídeos ainda sem canal
    identificado não aparecem (ver POST /reprocess/video-channels).
    """
    return list_channels_use_case(db=db, user_id=current_user.id)


@router.delete("/{youtube_id}")
def delete_video(
    youtube_id: str,
    db: Session = Depends(get_db),
    search_service: SemanticSearchService = Depends(get_search_service),
    current_user: User = Depends(get_current_active_user)
):
    """
    Remove o vídeo e todos os seus comentários (PostgreSQL + ChromaDB).
    """
    result = delete_video_use_case(db, youtube_id, search_service, current_user.id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Vídeo '{youtube_id}' não encontrado.")
    return result
