from sqlalchemy.orm import Session
from app.models.VideoModel import Video
from typing import List

def list_videos_use_case(db: Session, user_id: int) -> List[Video]:
    """
    Use case para listar todos os vídeos do utilizador.
    """
    print(f"--- [API/Use Case] A buscar vídeos do utilizador {user_id}... ---")
    
    videos = db.query(Video).filter(Video.user_id == user_id).all()
    
    return videos