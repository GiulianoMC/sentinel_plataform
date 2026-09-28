# app/repositories/InsightsRepository.py
"""
Repository do Módulo de Insights.

Faz o lado Postgres do "retrieve-then-join": o Chroma devolve ids ordenados por
similaridade e aqui se buscam os campos estruturados correspondentes. Também
concentra a amostragem estratificada usada pela estratégia 'sample' e o cache
dos cards de insights.
"""

from datetime import datetime
from typing import Dict, List, Optional, Union

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.models.VideoInsightModel import VideoInsight
from app.models.VideoModel import Comment, Video


class InsightsRepository:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ join

    def get_comments_by_ids(self, ids: List[str], youtube_id: Optional[str] = None) -> List[Comment]:
        """Devolve os comentários na mesma ordem de `ids` (ordem de relevância do Chroma).

        `IN` não preserva ordem, por isso a reordenação é feita em Python. Ids
        sem correspondência no Postgres são omitidos (fonte da verdade é o Postgres).
        `youtube_id` restringe o resultado a um vídeo — obrigatório quando os ids
        vêm do cliente, para que ninguém leia comentários de vídeos alheios.
        """
        if not ids:
            return []
        query = self.db.query(Comment).filter(Comment.id.in_(ids))
        if youtube_id is not None:
            query = query.filter(Comment.youtube_id == youtube_id)
        rows = query.all()
        by_id = {c.id: c for c in rows}
        return [by_id[cid] for cid in ids if cid in by_id]

    # -------------------------------------------------------------- amostragem

    @staticmethod
    def _apply_filters(query: Query, filters=None) -> Query:
        """Aplica os InsightFilters como WHERE no Postgres."""
        if not filters:
            return query
        if filters.sentiment_min is not None:
            query = query.filter(Comment.sentiment >= filters.sentiment_min)
        if filters.sentiment_max is not None:
            query = query.filter(Comment.sentiment <= filters.sentiment_max)
        if filters.intent:
            query = query.filter(Comment.intent == filters.intent)
        if filters.product:
            query = query.filter(
                func.lower(func.trim(Comment.product_mentioned)) == filters.product.lower().strip()
            )
        return query

    def sample_comments(
        self, video_ids: Union[str, List[str]], limit: int, filters=None
    ) -> List[Comment]:
        """Até `limit` comentários analisados, balanceados por sentimento (e por vídeo).

        Perguntas genéricas ("faça um resumo") não têm âncora semântica; uma
        amostra estratificada por nota evita que o contexto fique enviesado para
        o sentimento mais frequente. Window function (row_number) funciona em
        PostgreSQL e em SQLite >= 3.25.

        `video_ids` é um youtube_id ou a lista de youtube_ids de um canal. Com
        vários vídeos a partição passa a (vídeo, sentimento) e a ordem final é
        "primeiro de cada balde antes do segundo de qualquer balde": sem isso, a
        ordenação por data devolveria só o vídeo mais recente do canal.
        """
        ids = [video_ids] if isinstance(video_ids, str) else list(video_ids)
        if not ids:
            return []
        per_bucket = max(limit // (5 * len(ids)), 1)

        rn = func.row_number().over(
            partition_by=(Comment.youtube_id, Comment.sentiment),
            order_by=Comment.published_at.desc()
        ).label("rn")

        ranked = self._apply_filters(
            self.db.query(Comment.id.label("id"), rn).filter(
                Comment.youtube_id.in_(ids),
                Comment.sentiment.isnot(None),
                Comment.intent != "Erro_IA",
            ),
            filters,
        ).subquery()

        query = (
            self.db.query(Comment)
            .join(ranked, ranked.c.id == Comment.id)
            .filter(ranked.c.rn <= per_bucket)
        )
        if len(ids) > 1:
            query = query.order_by(ranked.c.rn, Comment.published_at.desc())
        else:
            query = query.order_by(Comment.published_at.desc())
        return query.limit(limit).all()

    def get_video_titles(self, youtube_ids) -> Dict[str, str]:
        """{youtube_id: titulo} para as fontes do /ask dizerem de que vídeo vêm."""
        ids = list({i for i in youtube_ids if i})
        if not ids:
            return {}
        rows = self.db.query(Video.youtube_id, Video.titulo).filter(Video.youtube_id.in_(ids)).all()
        return {yt: titulo for yt, titulo in rows}

    def count_analyzed(self, youtube_id: str) -> int:
        """Comentários efetivamente analisados (exclui os que ficaram em Erro_IA)."""
        return (
            self.db.query(func.count(Comment.id))
            .filter(
                Comment.youtube_id == youtube_id,
                Comment.sentiment.isnot(None),
                Comment.intent != "Erro_IA",
            )
            .scalar()
        ) or 0

    def ids_to_backfill(self, youtube_ids: List[str], batch_size: int = 500):
        """Itera os comentários já analisados dos vídeos indicados (para o backfill do Chroma)."""
        if not youtube_ids:
            return []
        return (
            self.db.query(Comment)
            .filter(Comment.youtube_id.in_(youtube_ids), Comment.sentiment.isnot(None))
            .yield_per(batch_size)
        )

    # -------------------------------------------------------------- cards

    def get_cards(self, youtube_id: str) -> List[VideoInsight]:
        return (
            self.db.query(VideoInsight)
            .filter(VideoInsight.youtube_id == youtube_id)
            .order_by(VideoInsight.kind)
            .all()
        )

    def upsert_card(
        self,
        youtube_id: str,
        kind: str,
        status: str,
        content: Optional[str] = None,
        evidence_ids: Optional[List[str]] = None,
        analyzed_at_generation: int = 0,
    ) -> VideoInsight:
        """Cria ou atualiza um card. Não faz commit — quem chama controla a transação."""
        card = (
            self.db.query(VideoInsight)
            .filter(VideoInsight.youtube_id == youtube_id, VideoInsight.kind == kind)
            .first()
        )
        if card is None:
            card = VideoInsight(youtube_id=youtube_id, kind=kind)
            self.db.add(card)

        card.status = status
        card.analyzed_at_generation = analyzed_at_generation
        if status == "pending":
            # Marca o pedido: é este timestamp que expira o lock de geração concorrente.
            card.requested_at = datetime.utcnow()
        elif status == "ready":
            card.content = content
            card.evidence_ids = evidence_ids
            card.generated_at = datetime.utcnow()
        # status "error": preserva o conteúdo anterior (o painel continua a mostrá-lo)
        return card

    def delete_cards(self, youtube_id: str) -> int:
        return (
            self.db.query(VideoInsight)
            .filter(VideoInsight.youtube_id == youtube_id)
            .delete(synchronize_session=False)
        )
