# app/use_cases/Insights/suggested_questions.py
"""
Perguntas sugeridas para o painel — determinísticas, sem custo de LLM.

Cada sugestão já vem com a estratégia e os filtros que fazem a pergunta funcionar
no /ask, de modo que clicar numa sugestão nunca cai em "sem evidência".

Funciona para um vídeo (`youtube_id`) ou para um canal (`channel_id` + `user_id`):
os agregados vêm dos métodos correspondentes do AnalyticsRepository e o texto troca
"deste vídeo" por "deste canal". No canal entram ainda perguntas comparativas que
só fazem sentido com vários vídeos.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.repositories.AnalyticsRepository import AnalyticsRepository

MAX_QUESTIONS = 5
MIN_PRODUCT_MENTIONS = 3

FALLBACK: Dict[str, Any] = {
    "question": "Faça um resumo geral dos comentários deste vídeo",
    "reason": "fallback",
    "strategy": "sample",
    "filters": None,
}

CHANNEL_FALLBACK: Dict[str, Any] = {**FALLBACK, "question": "Faça um resumo geral dos comentários deste canal"}


def _video_metrics(repo: AnalyticsRepository, youtube_id: str) -> Optional[dict]:
    summary = repo.get_video_summary(youtube_id)
    if not summary:
        return None
    return {
        "summary": summary,
        "products": (repo.get_top_products(youtube_id, limit=3, min_mentions=MIN_PRODUCT_MENTIONS) or {}).get("products", []),
        "intentions": (repo.get_intentions_distribution(youtube_id) or {}).get("intentions", []),
        "total_videos": 1,
    }


def _channel_metrics(repo: AnalyticsRepository, channel_id: str, user_id: int) -> Optional[dict]:
    summary = repo.get_channel_summary(channel_id, user_id)
    if not summary:
        return None
    return {
        "summary": summary,
        "products": (repo.get_channel_top_products(channel_id, user_id, limit=3, min_mentions=MIN_PRODUCT_MENTIONS) or {}).get("products", []),
        "intentions": (repo.get_channel_intentions(channel_id, user_id) or {}).get("intentions", []),
        "total_videos": summary.get("total_videos", 0),
    }


def suggested_questions_use_case(
    db: Session,
    youtube_id: Optional[str] = None,
    *,
    channel_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    repo = AnalyticsRepository(db)
    is_channel = channel_id is not None
    fallback = CHANNEL_FALLBACK if is_channel else FALLBACK

    metrics = (
        _channel_metrics(repo, channel_id, user_id) if is_channel else _video_metrics(repo, youtube_id)
    )
    if not metrics or not metrics["summary"].get("analyzed_comments"):
        return [{**fallback, "reason": "sem_analise"}]

    products = metrics["products"]
    intentions = [i for i in metrics["intentions"] if i["intent"] != "Erro_IA"]
    avg = metrics["summary"].get("average_sentiment") or 0.0

    out: List[Dict[str, Any]] = []

    # 1) Produtos: o mais específico primeiro. product_name vem em lowercase do
    # repositório; o valor bruto vai no filtro e o .title() só no texto exibido.
    for p in products:
        name = p["product_name"]
        label = name.title()
        if p["average_sentiment"] < 2.5:
            out.append({
                "question": f"Por que o {label} está sendo criticado?",
                "reason": f"produto_critico:{name}",
                "strategy": "semantic",
                "filters": {"product": name, "sentiment_max": 2},
            })
        elif p["average_sentiment"] > 4.0:
            out.append({
                "question": f"O que os usuários gostam no {label}?",
                "reason": f"produto_elogiado:{name}",
                "strategy": "semantic",
                "filters": {"product": name, "sentiment_min": 4},
            })

    # 2) Intenção dominante
    dominant = intentions[0]["intent"] if intentions else None
    if dominant == "Duvida":
        out.append({
            "question": "Quais dúvidas aparecem com mais frequência?",
            "reason": "duvidas_dominantes",
            "strategy": "sample",
            "filters": {"intent": "Duvida"},
        })
    elif dominant == "Intencao_Compra":
        out.append({
            "question": "O que está motivando a intenção de compra?",
            "reason": "intencao_compra_dominante",
            "strategy": "sample",
            "filters": {"intent": "Intencao_Compra"},
        })

    # 3) Só em canal com mais de um vídeo: comparações entre vídeos. Respondem-se
    # com a lista por vídeo dos metadados + amostra distribuída (strategy=sample).
    if is_channel and metrics["total_videos"] > 1:
        out.append({
            "question": "Qual vídeo teve a pior recepção e por quê?",
            "reason": "canal_comparar_videos",
            "strategy": "sample",
            "filters": None,
        })
        if products:
            out.append({
                "question": "Que produtos são comentados em mais de um vídeo?",
                "reason": "canal_produtos_transversais",
                "strategy": "sample",
                "filters": None,
            })

    # 4) Sentimento geral
    if avg < 2.5:
        out.append({
            "question": "Quais são as principais reclamações?",
            "reason": "sentimento_baixo",
            "strategy": "sample",
            "filters": {"sentiment_max": 2},
        })
    elif avg <= 3.5:
        out.append({
            "question": "O que divide as opiniões dos usuários?",
            "reason": "sentimento_misto",
            "strategy": "sample",
            "filters": None,
        })
    else:
        out.append({
            "question": "O que os usuários mais elogiam?",
            "reason": "sentimento_alto",
            "strategy": "sample",
            "filters": {"sentiment_min": 4},
        })

    # 5) Fallback genérico, sempre por último
    out.append(fallback)

    return out[:MAX_QUESTIONS]
