from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from app.models.VideoModel import Video


def list_channels_use_case(db: Session, user_id: int) -> List[dict]:
    """
    Canais distintos entre os vídeos do utilizador, com contagem de vídeos.
    Vídeos sem `channel_id` (registados antes do backfill) ficam de fora — o
    front usa /analytics/channels para saber quantos faltam identificar.

    `channel_title` pode variar entre vídeos do mesmo canal se o canal mudou de
    nome; usa-se MAX() só para escolher um valor determinístico por grupo.
    """
    rows = db.query(
        Video.channel_id.label("channel_id"),
        func.max(Video.channel_title).label("channel_title"),
        func.count(Video.id).label("video_count"),
    ).filter(
        Video.user_id == user_id,
        Video.channel_id.isnot(None),
    ).group_by(
        Video.channel_id
    ).order_by(
        func.count(Video.id).desc(),
        func.max(Video.channel_title),
    ).all()

    return [
        {"channel_id": r.channel_id, "channel_title": r.channel_title, "video_count": r.video_count}
        for r in rows
    ]
