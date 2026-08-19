from typing import List
from sqlalchemy.orm import Session
from app.models.VideoModel import Video


def get_user_video_ids(db: Session, user_id: int) -> List[str]:
    """Retorna lista de youtube_ids dos vídeos do usuário."""
    videos = db.query(Video.youtube_id).filter(Video.user_id == user_id).all()
    return [v[0] for v in videos]