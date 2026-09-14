from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.VideoModel import Video
import re
from typing import Optional

from app.utils import youtube_client

TITULO_DESCONHECIDO = "Título Desconhecido"


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


def _fetch_snippet(video_id: str) -> Optional[dict]:
    """
    Busca título, canal e data de publicação na API do YouTube.
    Devolve None quando a API não está configurada ou o vídeo não existe.
    """
    snippet = youtube_client.fetch_video_snippet(video_id)
    if snippet is None:
        print(f"--- [API/Use Case] Snippet indisponível para {video_id} (API não configurada ou vídeo não encontrado). ---")
    return snippet


def register_video_use_case(db: Session, video_url: str, titulo: Optional[str] = None, user_id: int = None):
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

    # O snippet é buscado sempre (mesmo com título fornecido) porque é a única
    # fonte do canal; sem ele o vídeo não entra no filtro por canal.
    snippet = _fetch_snippet(youtube_id) or {}

    titulo_final = titulo or snippet.get("title")
    if not titulo_final:
        print(f"--- [API/Use Case] Não foi possível obter o título. A usar '{TITULO_DESCONHECIDO}'. ---")
        titulo_final = TITULO_DESCONHECIDO
            
    novo_video = Video(
        youtube_id=youtube_id,
        titulo=titulo_final,
        channel_id=snippet.get("channel_id"),
        channel_title=snippet.get("channel_title"),
        published_at=snippet.get("published_at"),
        user_id=user_id
    )
    
    db.add(novo_video)
    try:
        db.commit()
    except IntegrityError:
        # Corrida: outro utilizador registou o mesmo youtube_id entre o check e o commit
        db.rollback()
        raise ValueError(f"O Video ID '{youtube_id}' já está registado.")
    db.refresh(novo_video)

    print(f"--- [API/Use Case] Novo vídeo registado: {youtube_id} (Título: {titulo_final}, Canal: {novo_video.channel_title or '?'}) ---")

    # Dispara coleta imediatamente para este video específico
    try:
        from app.celery.collector_tasks import coletar_comentarios_video_especifico
        coletar_comentarios_video_especifico.delay(youtube_id, user_id)
        print(f"--- [API/Use Case] Coleta imediata disparada para {youtube_id} ---")
    except Exception as e:
        print(f"--- [API/Use Case] Aviso: não foi possível disparar coleta imediata: {e} ---")

    return novo_video
