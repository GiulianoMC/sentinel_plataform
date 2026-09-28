# app/use_cases/Insights/insight_cards.py
"""
Leitura dos cards de insights em cache e decisão de regeneração.

Os cards são gerados por LLM (4 chamadas) e guardados no Postgres; o painel lê
sempre do cache. A regeneração só acontece quando entra volume novo de
comentários analisados suficiente para mudar as conclusões.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.VideoInsightModel import CARD_KINDS
from app.repositories.InsightsRepository import InsightsRepository

# Abaixo disto os cards sairiam fracos demais para valer a chamada de LLM.
MIN_ANALYZED_TO_GENERATE = 5
# Lock: um card 'pending' mais antigo que isto vem de uma task que morreu.
GENERATION_LOCK_MINUTES = 10
STALE_RATIO = 1.2
STALE_FLOOR = 10


def is_stale(analyzed_now: int, analyzed_at_generation: int) -> bool:
    """True quando entrou volume novo suficiente para justificar regenerar.

    O piso absoluto de 10 evita que volumes pequenos fiquem stale de imediato
    (int(3 * 1.2) == 3 marcaria stale com um único comentário novo).
    """
    if analyzed_at_generation <= 0:
        return analyzed_now > 0
    return analyzed_now > max(analyzed_at_generation * STALE_RATIO, analyzed_at_generation + STALE_FLOOR)


def _enqueue_generation(db: Session, repo: InsightsRepository, youtube_id: str, analyzed_now: int) -> bool:
    """Marca os cards como 'pending' e enfileira a geração.

    A marcação é commitada ANTES do enfileiramento: é ela que serve de lock
    contra gerações concorrentes disparadas por dois carregamentos do painel.
    """
    if analyzed_now < MIN_ANALYZED_TO_GENERATE:
        return False

    for kind in CARD_KINDS:
        repo.upsert_card(youtube_id, kind, status="pending", analyzed_at_generation=analyzed_now)
    db.commit()

    from app.celery.insight_tasks import generate_video_insights
    generate_video_insights.delay(youtube_id)
    return True


def get_insight_cards_use_case(
    db: Session,
    youtube_id: str,
    force: bool = False,
) -> dict:
    """Devolve os cards atuais e, se necessário, dispara a regeneração.

    O conteúdo antigo continua visível enquanto `generating` é True.
    Com `force=True` ignora o staleness (botão "atualizar insights"), mas
    continua a respeitar uma geração já em curso.
    """
    repo = InsightsRepository(db)
    cards = repo.get_cards(youtube_id)
    analyzed_now = repo.count_analyzed(youtube_id)

    lock_limit = datetime.utcnow() - timedelta(minutes=GENERATION_LOCK_MINUTES)
    generating = any(
        c.status == "pending" and c.requested_at is not None and c.requested_at > lock_limit
        for c in cards
    )

    ready = [c.analyzed_at_generation or 0 for c in cards if c.status == "ready"]
    stale = is_stale(analyzed_now, max(ready) if ready else 0)

    if (force or stale) and not generating:
        if _enqueue_generation(db, repo, youtube_id, analyzed_now):
            generating = True
            cards = repo.get_cards(youtube_id)

    return {
        "youtube_id": youtube_id,
        "cards": cards,
        "stale": stale,
        "generating": generating,
        "analyzed_now": analyzed_now,
    }
