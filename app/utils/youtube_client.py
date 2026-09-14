"""
Cliente partilhado da YouTube Data API v3.

Antes cada módulo construía o seu próprio `build('youtube', 'v3', ...)`. Este
módulo centraliza a criação (lazy, uma vez por processo) e oferece o helper
`fetch_video_snippets`, usado tanto no registo de vídeos como no backfill de
canais: recebe N ids, faz as chamadas em lotes de 50 (limite da API) e devolve
um dicionário normalizado por id.

Degrada graciosamente quando `YOUTUBE_API_KEY` não está definida: devolve
`None`/{} em vez de levantar, coerente com o collector e o register_video.
"""

import os
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# A API aceita no máximo 50 ids por chamada a videos().list
YOUTUBE_MAX_IDS_PER_CALL = 50

_service = None
_service_built = False


def get_youtube_service():
    """Devolve o cliente da API (ou None se a chave não estiver configurada)."""
    global _service, _service_built
    if _service_built:
        return _service
    _service_built = True
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("[YouTube] AVISO: YOUTUBE_API_KEY não definida. Metadados de vídeo/canal indisponíveis.")
        return None
    _service = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
    return _service


def parse_youtube_datetime(value: Optional[str]) -> Optional[datetime]:
    """
    Converte o ISO-8601 da API ('2024-01-01T12:00:00Z') para datetime naive em UTC,
    o formato guardado nas colunas DateTime (sem timezone) do Postgres.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _normalize_snippet(snippet: dict) -> dict:
    return {
        "title": snippet.get("title"),
        "channel_id": snippet.get("channelId"),
        "channel_title": snippet.get("channelTitle"),
        "published_at": parse_youtube_datetime(snippet.get("publishedAt")),
    }


def fetch_video_snippets(video_ids: Iterable[str]) -> Dict[str, dict]:
    """
    Busca o snippet de vários vídeos e devolve {youtube_id: {title, channel_id,
    channel_title, published_at}}. Ids inexistentes/privados simplesmente não
    aparecem no resultado. Devolve {} se a API não estiver configurada.
    """
    ids: List[str] = [v for v in dict.fromkeys(video_ids) if v]
    if not ids:
        return {}

    service = get_youtube_service()
    if service is None:
        return {}

    result: Dict[str, dict] = {}
    for start in range(0, len(ids), YOUTUBE_MAX_IDS_PER_CALL):
        batch = ids[start:start + YOUTUBE_MAX_IDS_PER_CALL]
        try:
            response = service.videos().list(part="snippet", id=",".join(batch)).execute()
        except HttpError as e:
            print(f"[YouTube] Erro ao buscar snippets ({len(batch)} ids): {e}")
            continue
        for item in response.get("items", []):
            video_id = item.get("id")
            snippet = item.get("snippet") or {}
            if video_id:
                result[video_id] = _normalize_snippet(snippet)
    return result


def fetch_video_snippet(video_id: str) -> Optional[dict]:
    """Atalho para um único vídeo. None se não encontrado ou API indisponível."""
    return fetch_video_snippets([video_id]).get(video_id)
