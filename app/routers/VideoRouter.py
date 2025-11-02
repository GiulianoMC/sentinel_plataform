from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from typing import Optional # Importamos o 'Optional'

from app.use_cases.Video.register_video import register_video_use_case

router = APIRouter(
    prefix="/video",
    tags=["Vídeos"]
)

class VideoRegisterRequest(BaseModel):
    video_url: str
    titulo: Optional[str] = None # Mudança aqui

@router.post("/register")
def register_video(
    request: VideoRegisterRequest, 
    db: Session = Depends(get_db)
):
    """
    Endpoint para registar um novo vídeo do YouTube
    a partir de um URL para ser monitorizado.
    """
    try:
        video_registado = register_video_use_case(
            db=db, 
            video_url=request.video_url,
            titulo=request.titulo
        )
        return video_registado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro inesperado: {e}")