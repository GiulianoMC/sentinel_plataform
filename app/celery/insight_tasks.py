# app/celery/insight_tasks.py
"""
Geração dos cards de insights (fila 'ai').

Reutiliza integralmente o pipeline RAG da Fase 3. Todos os cards usam perguntas
genéricas com strategy='sample', portanto este worker NÃO precisa do ChromaDB nem
do sentence-transformer — `search_service=None` mantém o worker_ai leve.
"""

from .celery_app import celery
from app.database import SessionLocal
from app.models.VideoInsightModel import CARD_KINDS
from app.repositories.InsightsRepository import InsightsRepository
from app.schemas.InsightsSchema import AskRequest
from app.services.LLMService import LLMService, LLMRateLimitError
from app.use_cases.Insights.ask_insight import ask_insight_use_case

llm_service = LLMService()

# Sem busca vetorial: todos os cards partem de amostra estratificada no Postgres.
search_service = None

CARD_SPECS = {
    "resumo": dict(
        question="Faça um resumo geral dos comentários deste vídeo.",
        strategy="sample", filters=None,
    ),
    "reclamacao_principal": dict(
        question="Quais são as principais reclamações dos usuários?",
        strategy="sample", filters={"sentiment_max": 2},
    ),
    "elogio_principal": dict(
        question="O que os usuários mais elogiam?",
        strategy="sample", filters={"sentiment_min": 4},
    ),
    "duvidas": dict(
        question="Quais dúvidas aparecem com mais frequência?",
        strategy="sample", filters={"intent": "Duvida"},
    ),
}


@celery.task(bind=True, max_retries=5, default_retry_delay=60)
def generate_video_insights(self, youtube_id: str):
    """Gera os 4 cards de um vídeo, um commit por card.

    O commit individual garante que um rate limit no terceiro card não perde os
    dois primeiros; o retry só refaz os que continuarem 'pending'.
    """
    print(f"--- [INSIGHTS] A gerar cards para o vídeo {youtube_id} ---")
    db = SessionLocal()
    gerados = 0

    try:
        repo = InsightsRepository(db)
        analyzed_now = repo.count_analyzed(youtube_id)

        for kind in CARD_KINDS:
            spec = CARD_SPECS[kind]
            card = next((c for c in repo.get_cards(youtube_id) if c.kind == kind), None)
            if card is not None and card.status == "ready" and card.analyzed_at_generation == analyzed_now:
                # Já refeito neste mesmo volume (retry parcial): não gasta LLM de novo.
                continue

            try:
                resposta = ask_insight_use_case(
                    db, search_service, llm_service, youtube_id, AskRequest(**spec)
                )
                repo.upsert_card(
                    youtube_id, kind,
                    status="ready",
                    content=resposta.answer,
                    evidence_ids=[s.id for s in resposta.sources],
                    analyzed_at_generation=analyzed_now,
                )
                db.commit()
                gerados += 1

            except LLMRateLimitError as e:
                db.rollback()
                print(f"[INSIGHTS] Rate limit no card {kind} de {youtube_id} — retry em {e.retry_after_seconds}s.")
                raise self.retry(exc=e, countdown=e.retry_after_seconds)

            except Exception as e:
                db.rollback()
                repo.upsert_card(youtube_id, kind, status="error", analyzed_at_generation=analyzed_now)
                db.commit()
                print(f"[INSIGHTS] Falha no card {kind} de {youtube_id}: {e}")

        print(f"--- [INSIGHTS] {gerados} cards gerados para {youtube_id}. ---")
        return f"{gerados} cards gerados para {youtube_id}"

    finally:
        db.close()
