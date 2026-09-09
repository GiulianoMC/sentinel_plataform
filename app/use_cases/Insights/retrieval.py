# app/use_cases/Insights/retrieval.py
"""
Estratégias de retrieval do RAG e montagem do contexto.

A busca vetorial só funciona quando a pergunta tem conteúdo semântico comparável
ao de um comentário. "Faça um resumo geral" não tem — por isso existem três
estratégias:

- semantic: busca no Chroma + join no Postgres (pergunta específica);
- sample:   amostra estratificada por sentimento no Postgres (pergunta genérica);
- auto:     tenta semantic e cai para sample se houver pouca evidência.
"""

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.VideoModel import Comment
from app.repositories.InsightsRepository import InsightsRepository

# Cada comentário entra truncado no prompt; o total limita o custo por pergunta.
MAX_COMMENT_CHARS = 300
MAX_CONTEXT_CHARS = 15_000        # ~4k tokens
N_RESULTS = MAX_CONTEXT_CHARS // MAX_COMMENT_CHARS   # 50
# Abaixo disto a resposta semântica seria frágil; 'auto' prefere a amostra.
MIN_EVIDENCE = 3
DEFAULT_THRESHOLD = 0.6


def retrieve(
    db: Session,
    search_service,
    youtube_id: str,
    question: str,
    strategy: str = "auto",
    filters=None,
) -> Tuple[List[Comment], Dict[str, float], str]:
    """Devolve (comentários, distâncias por id, estratégia efetivamente usada).

    `search_service` pode ser None (worker de IA, que não carrega o
    sentence-transformer): nesse caso só a estratégia 'sample' é possível.
    """
    repo = InsightsRepository(db)

    if strategy in ("auto", "semantic") and search_service is not None:
        hits = search_service.search(
            query=question,
            video_id_filter=youtube_id,
            num_results=N_RESULTS,
            threshold=DEFAULT_THRESHOLD,
            extra_where=filters.to_chroma_where() if filters else None,
        )
        comments = repo.get_comments_by_ids([h["id"] for h in hits])
        if comments and (strategy == "semantic" or len(comments) >= MIN_EVIDENCE):
            return comments, {h["id"]: h["distancia"] for h in hits}, "semantic"
        if strategy == "semantic":
            # Estratégia explícita: não mascara a ausência de evidência com uma amostra.
            return [], {}, "semantic"

    comments = repo.sample_comments(youtube_id, limit=N_RESULTS, filters=filters)
    return comments, {}, "sample"


def build_context(comments: List[Comment]) -> Tuple[str, List[Comment]]:
    """Monta o bloco de comentários do prompt respeitando o orçamento de tokens.

    Devolve o texto e a lista de comentários que realmente entraram — é essa
    lista que define a numeração [1], [2], ... citada na resposta.
    """
    lines: List[str] = []
    used: List[Comment] = []
    total = 0

    for c in comments:
        text = (c.text or "").strip().replace("\n", " ")[:MAX_COMMENT_CHARS]
        line = (
            f"[{len(used) + 1}] (sentimento={c.sentiment}, intenção={c.intent}, "
            f"produto={c.product_mentioned or '-'}) {text}"
        )
        if total + len(line) > MAX_CONTEXT_CHARS:
            break
        lines.append(line)
        used.append(c)
        total += len(line)

    return "\n".join(lines), used
