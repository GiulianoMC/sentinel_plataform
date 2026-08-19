# app/repositories/AnalyticsRepository.py
"""
Repository para operações de Analytics no PostgreSQL.
Todas as agregações são feitas no banco de dados (SQLAlchemy func).
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List, Tuple
from app.models.VideoModel import Comment, Video


class AnalyticsRepository:
    """
    Repository para queries analíticas otimizadas.
    Todas as operações usam agregação SQL (COUNT, AVG, GROUP BY) no PostgreSQL.
    """

    def __init__(self, db: Session):
        self.db = db

    def _video_exists(self, youtube_id: str) -> bool:
        """Verifica se o vídeo existe no banco."""
        return self.db.query(Video).filter(Video.youtube_id == youtube_id).first() is not None

    def get_video_summary(self, youtube_id: str) -> Optional[dict]:
        """
        Retorna resumo do vídeo: total de comentários, analisados e sentimento médio.

        Args:
            youtube_id: ID do vídeo no YouTube

        Returns:
            Dicionário com total_comments, analyzed_comments, average_sentiment
            ou None se o vídeo não existir
        """
        if not self._video_exists(youtube_id):
            return None

        # Query otimizada: COUNT total, COUNT analisados (sentiment IS NOT NULL), AVG sentiment
        result = self.db.query(
            func.count(Comment.id).label('total_comments'),
            func.count(Comment.sentiment).label('analyzed_comments'),
            func.avg(Comment.sentiment).label('average_sentiment')
        ).filter(Comment.youtube_id == youtube_id).first()

        return {
            'youtube_id': youtube_id,
            'total_comments': result.total_comments or 0,
            'analyzed_comments': result.analyzed_comments or 0,
            'average_sentiment': float(result.average_sentiment) if result.average_sentiment else None
        }

    def get_intentions_distribution(self, youtube_id: str) -> Optional[dict]:
        """
        Retorna distribuição de intenções (agrupadas por intent).

        Args:
            youtube_id: ID do vídeo no YouTube

        Returns:
            Dicionário com youtube_id e lista de intenções ordenadas por count (desc)
            ou None se o vídeo não existir
        """
        if not self._video_exists(youtube_id):
            return None

        # Query otimizada: GROUP BY intent, COUNT(*), ignorando NULLs
        results = self.db.query(
            Comment.intent.label('intent'),
            func.count(Comment.id).label('count')
        ).filter(
            Comment.youtube_id == youtube_id,
            Comment.intent.isnot(None)  # Ignora nulos
        ).group_by(
            Comment.intent
        ).order_by(
            desc('count')  # Ordena do maior para o menor
        ).all()

        intentions_list = [
            {'intent': row.intent, 'count': row.count}
            for row in results
        ]

        return {
            'youtube_id': youtube_id,
            'intentions': intentions_list
        }

    def get_top_products(
        self,
        youtube_id: str,
        limit: int = 5,
        min_mentions: int = 1
    ) -> Optional[dict]:
        """
        Retorna os produtos mais mencionados com contagem e sentimento médio.

        Args:
            youtube_id: ID do vídeo no YouTube
            limit: Número máximo de produtos a retornar (padrão: 5)
            min_mentions: Número mínimo de menções para incluir (padrão: 1)

        Returns:
            Dicionário com youtube_id e lista de produtos ordenados por count (desc)
            ou None se o vídeo não existir
        """
        if not self._video_exists(youtube_id):
            return None

        # Normaliza para lowercase+trim antes de agrupar para consolidar variantes de capitalização
        normalized = func.lower(func.trim(Comment.product_mentioned))

        results = self.db.query(
            normalized.label('product_name'),
            func.count(Comment.id).label('count'),
            func.avg(Comment.sentiment).label('average_sentiment')
        ).filter(
            Comment.youtube_id == youtube_id,
            Comment.product_mentioned.isnot(None)
        ).group_by(
            normalized
        ).having(
            func.count(Comment.id) >= min_mentions
        ).order_by(
            desc('count')  # Ordena do maior para o menor
        ).limit(limit).all()

        products_list = [
            {
                'product_name': row.product_name,
                'count': row.count,
                'average_sentiment': float(row.average_sentiment) if row.average_sentiment else 0.0
            }
            for row in results
        ]

        return {
            'youtube_id': youtube_id,
            'products': products_list
        }

    def get_sentiment_distribution(self, youtube_id: str) -> Optional[dict]:
        """
        Retorna distribuição de sentimentos (1-5) para um vídeo.

        Args:
            youtube_id: ID do vídeo no YouTube

        Returns:
            Dicionário com youtube_id e distribuição de sentimentos
            ou None se o vídeo não existir
        """
        if not self._video_exists(youtube_id):
            return None

        results = self.db.query(
            Comment.sentiment.label('sentiment'),
            func.count(Comment.id).label('count')
        ).filter(
            Comment.youtube_id == youtube_id,
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

        return {
            'youtube_id': youtube_id,
            'distribution': distribution
        }

    def get_overview(self, user_id: int) -> dict:
        """
        Retorna visão geral de todos os vídeos do usuário: totais agregados
        e dados por vídeo (total/analisados/sentimento médio).

        Uma única query: LEFT JOIN vídeos -> comentários com GROUP BY v.id;
        a média geral de sentimento é calculada no Python, ponderada pela
        quantidade de comentários analisados de cada vídeo.

        Args:
            user_id: ID do usuário autenticado

        Returns:
            Dicionário com total_videos, total_comments, analyzed_comments,
            average_sentiment e lista de vídeos
        """
        results = self.db.query(
            Video.youtube_id.label('youtube_id'),
            Video.titulo.label('titulo'),
            Video.created_at.label('created_at'),
            func.count(Comment.id).label('total_comments'),
            func.count(Comment.sentiment).label('analyzed_comments'),
            func.avg(Comment.sentiment).label('average_sentiment')
        ).outerjoin(
            Comment, Comment.youtube_id == Video.youtube_id
        ).filter(
            Video.user_id == user_id
        ).group_by(
            Video.id
        ).order_by(
            Video.created_at
        ).all()

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
                'created_at': row.created_at,
                'total_comments': row_total,
                'analyzed_comments': row_analyzed,
                'average_sentiment': row_avg,
            })

        average_sentiment = (
            round(weighted_sentiment_sum / analyzed_comments, 2) if analyzed_comments > 0 else None
        )

        return {
            'total_videos': len(videos),
            'total_comments': total_comments,
            'analyzed_comments': analyzed_comments,
            'average_sentiment': average_sentiment,
            'videos': videos,
        }
