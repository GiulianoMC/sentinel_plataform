from sqlalchemy.orm import Session
from app.models.VideoModel import Video
from typing import List, Optional

def list_videos_use_case(db: Session, user_id: int, channel_id: Optional[str] = None) -> List[Video]:
    """
    Use case para listar os vídeos do utilizador, opcionalmente só os de um canal.
    """
    print(f"--- [API/Use Case] A buscar vídeos do utilizador {user_id} (canal={channel_id or 'todos'})... ---")
    
    query = db.query(Video).filter(Video.user_id == user_id)
    if channel_id:
        query = query.filter(Video.channel_id == channel_id)

    return query.order_by(Video.created_at).all()
