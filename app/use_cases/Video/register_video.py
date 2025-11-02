from sqlalchemy.orm import Session
from app.models.VideoModel import Video
import re
from typing import Optional # Importamos o 'Optional'

def _extrair_video_id(url: str) -> Optional[str]: # Mudança aqui
    """
    Função helper para extrair o ID de um vídeo do YouTube
    de vários formatos de URL (watch?v=... e youtu.be/...)
    """
    regex = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    
    match = re.search(regex, url)
    
    if match:
        return match.group(1) 
    return None

def register_video_use_case(db: Session, video_url: str, titulo: Optional[str] = None): # Mudança aqui
    """
    Use case para registar um novo vídeo no banco de dados
    a partir de um URL.
    """
    
    youtube_id = _extrair_video_id(video_url)
    
    if not youtube_id:
        raise ValueError(f"URL do YouTube inválido ou ID não encontrado no link: '{video_url}'")

    video_existente = db.query(Video).filter(Video.youtube_id == youtube_id).first()
    
    if video_existente:
        raise ValueError(f"O Video ID '{youtube_id}' (extraído de {video_url}) já está registado.")
        
    novo_video = Video(
        youtube_id=youtube_id,
        titulo=titulo
    )
    
    db.add(novo_video)
    db.commit()
    db.refresh(novo_video)
    
    print(f"--- [API/Use Case] Novo vídeo registado: {youtube_id} ---")
    
    return novo_video