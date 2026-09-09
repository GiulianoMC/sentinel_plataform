# app/use_cases/Insights/suggested_questions.py
"""
Perguntas sugeridas para o painel — determinísticas, sem custo de LLM.

Cada sugestão já vem com a estratégia e os filtros que fazem a pergunta funcionar
no /ask, de modo que clicar numa sugestão nunca cai em "sem evidência".
"""

from typing import Any, Dict, List

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


def suggested_questions_use_case(db: Session, youtube_id: str) -> List[Dict[str, Any]]:
    repo = AnalyticsRepository(db)
    summary = repo.get_video_summary(youtube_id)

    if not summary or not summary.get("analyzed_comments"):
        return [{**FALLBACK, "reason": "sem_analise"}]

    products = (repo.get_top_products(youtube_id, limit=3, min_mentions=MIN_PRODUCT_MENTIONS) or {}).get("products", [])
    intentions = [
        i for i in (repo.get_intentions_distribution(youtube_id) or {}).get("intentions", [])
        if i["intent"] != "Erro_IA"
    ]
    avg = summary.get("average_sentiment") or 0.0

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

    # 3) Sentimento geral
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

    # 4) Fallback genérico, sempre por último
    out.append(FALLBACK)

    return out[:MAX_QUESTIONS]
