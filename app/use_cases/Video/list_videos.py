from sqlalchemy.orm import Session
from app.models.VideoModel import Video
from typing import List

def list_videos_use_case(db: Session) -> List[Video]:
    """
    Use case para listar todos os vídeos registados no banco de dados.
    """
    print("--- [API/Use Case] A buscar todos os vídeos registados... ---")
    
    # Simplesmente busca todos os registos da tabela 'videos'
    videos = db.query(Video).all()
    
    return videos