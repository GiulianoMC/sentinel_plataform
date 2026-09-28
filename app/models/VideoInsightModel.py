# app/models/VideoInsightModel.py
"""Cache dos cards de insights gerados por LLM, um registo por (vídeo, tipo)."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base

# Tipos de card gerados para cada vídeo (ver CARD_SPECS em app/celery/insight_tasks.py)
CARD_KINDS = ("resumo", "reclamacao_principal", "elogio_principal", "duvidas")


class VideoInsight(Base):
    __tablename__ = "video_insights"
    __table_args__ = (
        UniqueConstraint("youtube_id", "kind", name="uq_video_insights_video_kind"),
    )

    id = Column(Integer, primary_key=True, index=True)
    youtube_id = Column(
        String, ForeignKey("videos.youtube_id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    content = Column(Text, nullable=True)
    # ids dos comentários citados na resposta, para o front resolver as citações
    evidence_ids = Column(JSON, nullable=True)
    # quantos comentários analisados existiam quando o card foi gerado (base do staleness)
    analyzed_at_generation = Column(Integer, nullable=False, default=0)
    generated_at = Column(DateTime, nullable=True)
    requested_at = Column(DateTime, nullable=False, server_default=func.now())
