"""
Backfill de canal para vídeos já registados.

`channel_id` existe no schema desde a revisão 000 mas só passou a ser
preenchido no registo a partir da revisão 004. Este use case consulta a
YouTube API (videos().list, 50 ids por chamada — 1 unidade de quota cada)
para os vídeos do utilizador sem canal e grava channel_id/channel_title/
published_at. Também corrige títulos gravados como 'Título Desconhecido'.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.VideoModel import Video
from app.utils import youtube_client
from app.use_cases.Video.register_video import TITULO_DESCONHECIDO


class YouTubeApiUnavailable(Exception):
    """YOUTUBE_API_KEY não configurada — o backfill não tem como buscar os dados."""


def backfill_video_channels_use_case(
    db: Session,
    user_id: int,
    force: bool = False,
    youtube_id: Optional[str] = None,
) -> dict:
    """
    Args:
        user_id: só vídeos deste utilizador são tocados.
        force: True re-busca também os vídeos que já têm canal (ex: canal renomeado).
        youtube_id: restringe a um vídeo.

    Returns:
        {"total": n, "updated": n, "not_found": n, "message": str}
    """
    query = db.query(Video).filter(Video.user_id == user_id)
    if youtube_id:
        query = query.filter(Video.youtube_id == youtube_id)
    if not force:
        query = query.filter(Video.channel_id.is_(None))
    videos = query.all()

    if not videos:
        return {
            "total": 0, "updated": 0, "not_found": 0,
            "message": "Nenhum vídeo pendente de identificação de canal.",
        }

    if youtube_client.get_youtube_service() is None:
        raise YouTubeApiUnavailable("YOUTUBE_API_KEY não configurada; impossível consultar canais.")

    snippets = youtube_client.fetch_video_snippets([v.youtube_id for v in videos])

    updated = 0
    not_found = 0
    for video in videos:
        snippet = snippets.get(video.youtube_id)
        if not snippet:
            # Vídeo apagado/privado no YouTube, ou falha da API nesse lote.
            not_found += 1
            continue
        video.channel_id = snippet.get("channel_id")
        video.channel_title = snippet.get("channel_title")
        if snippet.get("published_at") and not video.published_at:
            video.published_at = snippet["published_at"]
        if snippet.get("title") and (not video.titulo or video.titulo == TITULO_DESCONHECIDO):
            video.titulo = snippet["title"]
        updated += 1

    db.commit()
    print(f"--- [API/Use Case] Backfill de canais (user {user_id}): {updated} atualizados, {not_found} não encontrados ---")

    return {
        "total": len(videos),
        "updated": updated,
        "not_found": not_found,
        "message": f"{updated} vídeo(s) atualizados; {not_found} não encontrados no YouTube.",
    }
