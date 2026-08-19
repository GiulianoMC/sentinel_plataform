# app/models/VideoModel.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True, index=True)
    youtube_id = Column(String, unique=True, index=True, nullable=False)
    titulo = Column(String, nullable=False)
    channel_id = Column(String, nullable=True)
    published_at = Column(DateTime, nullable=True)
    ultimo_comentario_verificado_em = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    comments = relationship("Comment", back_populates="video")
    owner = relationship("User", back_populates="videos")

class Comment(Base):
    __tablename__ = "comments"
    id = Column(String, primary_key=True, index=True)
    youtube_id = Column(String, ForeignKey("videos.youtube_id"), nullable=False)
    author = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    published_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    sentiment = Column(Integer, nullable=True)
    intent = Column(String, nullable=True) 
    product_mentioned = Column(String, nullable=True)
    # ------------------------------------

    video = relationship("Video", back_populates="comments")