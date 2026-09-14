# app/repositories/AnalyticsRepository.py
"""
Repository para operações de Analytics no PostgreSQL.
Todas as agregações são feitas no banco de dados (SQLAlchemy func).

Cada métrica existe em dois escopos: um vídeo (`youtube_id`) ou um canal
(`channel_id` + `user_id`, porque o mesmo canal pode ter vídeos registados
por utilizadores diferentes). A query de agregação é a mesma; só muda o
filtro aplicado por `_scoped_comments`.
"""

from sqlalchemy.orm import Session, Query
from sqlalchemy import func, desc
from typing import Optional
from app.models.VideoModel import Comment, Video


class _Scope:
    """Escopo de uma agregação: exatamente um de `youtube_id` ou `channel_id`."""

    def __init__(self, youtube_id: Optional[str] = None, channel_id: Optional[str] = None,
                 user_id: Optional[int] = None):
        self.youtube_id = youtube_id
        self.channel_id = channel_id
        self.user_id = user_id


class AnalyticsRepository:
    """
    Repository para queries analíticas otimizadas.
    Todas as operações usam agregação SQL (COUNT, AVG, GROUP BY) no PostgreSQL.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Escopo
    # ------------------------------------------------------------------

    def _video_exists(self, youtube_id: str) -> bool:
        """Verifica se o vídeo existe no banco."""
        return self.db.query(Video).filter(Video.youtube_id == youtube_id).first() is not None

    def _channel_videos(self, channel_id: str, user_id: int) -> Query:
        return self.db.query(Video).filter(Video.channel_id == channel_id, Video.user_id == user_id)

    def _channel_exists(self, channel_id: str, user_id: int) -> bool:
        """O canal 'existe' para o utilizador se ele tiver pelo menos um vídeo nele."""
        return self._channel_videos(channel_id, user_id).first() is not None

    def _scoped_comments(self, query: Query, scope: _Scope) -> Query:
        """Aplica o filtro do escopo a uma query sobre Comment."""
        if scope.youtube_id is not None:
            return query.filter(Comment.youtube_id == scope.youtube_id)
        return query.join(
            Video, Video.youtube_id == Comment.youtube_id
        ).filter(
            Video.channel_id == scope.channel_id,
            Video.user_id == scope.user_id,
        )

    # ------------------------------------------------------------------
    # Agregações (independentes do escopo)
    # ------------------------------------------------------------------

    def _summary(self, scope: _Scope) -> dict:
        # Query otimizada: COUNT total, COUNT analisados (sentiment IS NOT NULL), AVG sentiment
        result = self._scoped_comments(self.db.query(
            func.count(Comment.id).label('total_comments'),
            func.count(Comment.sentiment).label('analyzed_comments'),
            func.avg(Comment.sentiment).label('average_sentiment')
        ), scope).first()

        return {
            'total_comments': result.total_comments or 0,
            'analyzed_comments': result.analyzed_comments or 0,
            'average_sentiment': float(result.average_sentiment) if result.average_sentiment else None
        }

    def _intentions(self, scope: _Scope) -> list:
        # Query otimizada: GROUP BY intent, COUNT(*), ignorando NULLs
        results = self._scoped_comments(self.db.query(
            Comment.intent.label('intent'),
            func.count(Comment.id).label('count')
        ), scope).filter(
            Comment.intent.isnot(None)  # Ignora nulos
        ).group_by(
            Comment.intent
        ).order_by(
            desc('count')  # Ordena do maior para o menor
        ).all()

        return [{'intent': row.intent, 'count': row.count} for row in results]

    def _products(self, scope: _Scope, limit: int, min_mentions: int) -> list:
        # Normaliza para lowercase+trim antes de agrupar para consolidar variantes de capitalização
        normalized = func.lower(func.trim(Comment.product_mentioned))

        results = self._scoped_comments(self.db.query(
            normalized.label('product_name'),
            func.count(Comment.id).label('count'),
            func.avg(Comment.sentiment).label('average_sentiment')
        ), scope).filter(
            Comment.product_mentioned.isnot(None)
        ).group_by(
            normalized
        ).having(
            func.count(Comment.id) >= min_mentions
        ).order_by(
            desc('count')  # Ordena do maior para o menor
        ).limit(limit).all()

        return [
            {
                'product_name': row.product_name,
                'count': row.count,
                'average_sentiment': float(row.average_sentiment) if row.average_sentiment else 0.0
            }
            for row in results
        ]

    def _sentiment_distribution(self, scope: _Scope) -> dict:
        results = self._scoped_comments(self.db.query(
            Comment.sentiment.label('sentiment'),
            func.count(Comment.id).label('count')
        ), scope).filter(
            Comment.sentiment.isnot(None)
        ).group_by(
            Comment.sentiment
        ).order_by(
            Comment.sentiment
        ).all()

        # Cria dicionário com todas as notas 1-5 (mesmo as sem ocorrências)
        distribution = {str(i): 0 for i in range(1, 6)}
        for row in results:
            distribution[str(int(row.sentiment))] = row.count
        return distribution

    # ------------------------------------------------------------------
    # Por vídeo
    # ------------------------------------------------------------------

    def get_video_summary(self, youtube_id: str) -> Optional[dict]:
        """
        Retorna resumo do vídeo: total de comentários, analisados e sentimento médio,
        ou None se o vídeo não existir.
        """
        if not self._video_exists(youtube_id):
            return None
        return {'youtube_id': youtube_id, **self._summary(_Scope(youtube_id=youtube_id))}

    def get_intentions_distribution(self, youtube_id: str) -> Optional[dict]:
        """
        Retorna distribuição de intenções (agrupadas por intent), ordenadas por
        count (desc), ou None se o vídeo não existir.
        """
        if not self._video_exists(youtube_id):
            return None
        return {'youtube_id': youtube_id, 'intentions': self._intentions(_Scope(youtube_id=youtube_id))}

    def get_top_products(
        self,
        youtube_id: str,
        limit: int = 5,
        min_mentions: int = 1
    ) -> Optional[dict]:
        """
        Retorna os produtos mais mencionados com contagem e sentimento médio,
        ou None se o vídeo não existir.
        """
        if not self._video_exists(youtube_id):
            return None
        return {
            'youtube_id': youtube_id,
            'products': self._products(_Scope(youtube_id=youtube_id), limit, min_mentions)
        }

    def get_sentiment_distribution(self, youtube_id: str) -> Optional[dict]:
        """
        Retorna distribuição de sentimentos (1-5) para um vídeo,
        ou None se o vídeo não existir.
        """
        if not self._video_exists(youtube_id):
            return None
        return {
            'youtube_id': youtube_id,
            'distribution': self._sentiment_distribution(_Scope(youtube_id=youtube_id))
        }

    # ------------------------------------------------------------------
    # Por canal (sempre restrito aos vídeos do utilizador)
    # ------------------------------------------------------------------

    def get_channel_summary(self, channel_id: str, user_id: int) -> Optional[dict]:
        """
        Resumo agregado de todos os vídeos do utilizador num canal,
        ou None se o utilizador não tiver vídeos nesse canal.
        """
        if not self._channel_exists(channel_id, user_id):
            return None

        meta = self._channel_videos(channel_id, user_id).with_entities(
            func.max(Video.channel_title).label('channel_title'),
            func.count(Video.id).label('total_videos'),
        ).first()

        return {
            'channel_id': channel_id,
            'channel_title': meta.channel_title,
            'total_videos': meta.total_videos or 0,
            **self._summary(_Scope(channel_id=channel_id, user_id=user_id)),
        }

    def get_channel_intentions(self, channel_id: str, user_id: int) -> Optional[dict]:
        if not self._channel_exists(channel_id, user_id):
            return None
        return {
            'channel_id': channel_id,
            'intentions': self._intentions(_Scope(channel_id=channel_id, user_id=user_id))
        }

    def get_channel_top_products(
        self, channel_id: str, user_id: int, limit: int = 5, min_mentions: int = 1
    ) -> Optional[dict]:
        if not self._channel_exists(channel_id, user_id):
            return None
        return {
            'channel_id': channel_id,
            'products': self._products(_Scope(channel_id=channel_id, user_id=user_id), limit, min_mentions)
        }

    def get_channel_sentiment_distribution(self, channel_id: str, user_id: int) -> Optional[dict]:
        if not self._channel_exists(channel_id, user_id):
            return None
        return {
            'channel_id': channel_id,
            'distribution': self._sentiment_distribution(_Scope(channel_id=channel_id, user_id=user_id))
        }

    def get_channels_overview(self, user_id: int) -> dict:
        """
        Agregados por canal (vídeos, comentários, analisados, sentimento médio)
        para todos os canais do utilizador, mais a contagem de vídeos ainda
        sem canal identificado. Uma query com GROUP BY channel_id.
        """
        results = self.db.query(
            Video.channel_id.label('channel_id'),
            func.max(Video.channel_title).label('channel_title'),
            func.count(func.distinct(Video.id)).label('total_videos'),
            func.count(Comment.id).label('total_comments'),
            func.count(Comment.sentiment).label('analyzed_comments'),
            func.avg(Comment.sentiment).label('average_sentiment'),
        ).outerjoin(
            Comment, Comment.youtube_id == Video.youtube_id
        ).filter(
            Video.user_id == user_id
        ).group_by(
            Video.channel_id
        ).all()

        channels = []
        videos_without_channel = 0
        for row in results:
            if row.channel_id is None:
                videos_without_channel = row.total_videos or 0
                continue
            channels.append({
                'channel_id': row.channel_id,
                'channel_title': row.channel_title,
                'total_videos': row.total_videos or 0,
                'total_comments': row.total_comments or 0,
                'analyzed_comments': row.analyzed_comments or 0,
                'average_sentiment': (
                    round(float(row.average_sentiment), 2) if row.average_sentiment is not None else None
                ),
            })

        # Canais com mais comentários primeiro; empate por nome.
        channels.sort(key=lambda c: (-c['total_comments'], -c['total_videos'], c['channel_title'] or ''))

        return {
            'total_channels': len(channels),
            'videos_without_channel': videos_without_channel,
            'channels': channels,
        }

    # ------------------------------------------------------------------
    # Visão geral
    # ------------------------------------------------------------------

    def get_overview(self, user_id: int, channel_id: Optional[str] = None) -> dict:
        """
        Retorna visão geral dos vídeos do usuário (todos, ou só os de um canal):
        totais agregados e dados por vídeo (total/analisados/sentimento médio).

        Uma única query: LEFT JOIN vídeos -> comentários com GROUP BY v.id;
        a média geral de sentimento é calculada no Python, ponderada pela
        quantidade de comentários analisados de cada vídeo.

        Args:
            user_id: ID do usuário autenticado
            channel_id: se fornecido, restringe aos vídeos desse canal

        Returns:
            Dicionário com channel_id, total_videos, total_comments,
            analyzed_comments, average_sentiment e lista de vídeos
        """
        query = self.db.query(
            Video.youtube_id.label('youtube_id'),
            Video.titulo.label('titulo'),
            Video.channel_id.label('channel_id'),
            Video.channel_title.label('channel_title'),
            Video.created_at.label('created_at'),
            func.count(Comment.id).label('total_comments'),
            func.count(Comment.sentiment).label('analyzed_comments'),
            func.avg(Comment.sentiment).label('average_sentiment')
        ).outerjoin(
            Comment, Comment.youtube_id == Video.youtube_id
        ).filter(
            Video.user_id == user_id
        )
        if channel_id:
            query = query.filter(Video.channel_id == channel_id)

        results = query.group_by(Video.id).order_by(Video.created_at).all()

        videos = []
        total_comments = 0
        analyzed_comments = 0
        weighted_sentiment_sum = 0.0

        for row in results:
            row_total = row.total_comments or 0
            row_analyzed = row.analyzed_comments or 0
            row_avg = float(row.average_sentiment) if row.average_sentiment is not None else None

            total_comments += row_total
            analyzed_comments += row_analyzed
            if row_avg is not None:
                weighted_sentiment_sum += row_avg * row_analyzed

            videos.append({
                'youtube_id': row.youtube_id,
                'titulo': row.titulo,
                'channel_id': row.channel_id,
                'channel_title': row.channel_title,
                'created_at': row.created_at,
                'total_comments': row_total,
                'analyzed_comments': row_analyzed,
                'average_sentiment': row_avg,
            })

        average_sentiment = (
            round(weighted_sentiment_sum / analyzed_comments, 2) if analyzed_comments > 0 else None
        )

        return {
            'channel_id': channel_id,
            'total_videos': len(videos),
            'total_comments': total_comments,
            'analyzed_comments': analyzed_comments,
            'average_sentiment': average_sentiment,
            'videos': videos,
        }
