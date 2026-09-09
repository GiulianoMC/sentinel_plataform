from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.VideoModel import Video


def get_user_video_ids(db: Session, user_id: int) -> List[str]:
    """Retorna lista de youtube_ids dos vídeos do usuário."""
    videos = db.query(Video.youtube_id).filter(Video.user_id == user_id).all()
    return [v[0] for v in videos]

def get_owned_video(db: Session, youtube_id: str, user_id: int) -> Optional[Video]:
    """Retorna o vídeo se ele existir E pertencer ao usuário; caso contrário None.

    Ponto único de verificação de ownership: os routers respondem 404 quando o
    retorno é None, sem distinguir "não existe" de "não é seu" (evita enumeração).
    """
    return db.query(Video).filter(
        Video.youtube_id == youtube_id,
        Video.user_id == user_id
    ).first()
