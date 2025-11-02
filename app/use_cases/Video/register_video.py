from sqlalchemy.orm import Session
from app.models.VideoModel import Video
import re
from typing import Optional
import os

# Importações da API do Google
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
youtube_service = None
if YOUTUBE_API_KEY:
    youtube_service = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY, cache_discovery=False)
else:
    print("[API/Use Case] AVISO: YOUTUBE_API_KEY não definida. Não será possível buscar títulos de vídeos.")


def _extrair_video_id(url: str) -> Optional[str]:
    """
    Função helper para extrair o ID de um vídeo do YouTube
    de vários formatos de URL (watch?v=... e youtu.be/...)
    """
    regex = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    match = re.search(regex, url)
    if match:
        return match.group(1)
    return None

def _fetch_titulo_video(video_id: str) -> Optional[str]:
    """
    Busca o título de um vídeo na API do YouTube.
    """
    if not youtube_service:
        return None
    
    try:
        response = youtube_service.videos().list(
            part="snippet",
            id=video_id
        ).execute()
        
        items = response.get("items", [])
        if items:
            return items[0]["snippet"]["title"]
    except HttpError as e:
        print(f"Erro ao buscar título do vídeo {video_id}: {e}")
        return None
    return None

def register_video_use_case(db: Session, video_url: str, titulo: Optional[str] = None):
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
        
    # Lógica para buscar o título se ele não for fornecido
    titulo_final = titulo
    if not titulo_final:
        print(f"--- [API/Use Case] Título não fornecido. A buscar na API do YouTube... ---")
        titulo_final = _fetch_titulo_video(youtube_id)
        if not titulo_final:
            print(f"--- [API/Use Case] Não foi possível buscar o título. A usar 'Título Desconhecido'. ---")
            titulo_final = "Título Desconhecido"
            
    novo_video = Video(
        youtube_id=youtube_id,
        titulo=titulo_final
    )
    
    db.add(novo_video)
    db.commit()
    db.refresh(novo_video)
    
    print(f"--- [API/Use Case] Novo vídeo registado: {youtube_id} (Título: {titulo_final}) ---")
    
    return novo_video