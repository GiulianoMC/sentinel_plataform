# app/use_cases/Insights/ask_insight.py
"""Pipeline RAG: retrieval -> contexto (agregados + comentários) -> LLM com citações."""

import re
from typing import List, Optional

from sqlalchemy.orm import Session

from app.repositories.AnalyticsRepository import AnalyticsRepository
from app.schemas.InsightsSchema import AskRequest, AskResponse, SourceComment
from app.use_cases.Insights.retrieval import MAX_COMMENT_CHARS, build_context, retrieve

NO_EVIDENCE = (
    "Não encontrei evidências suficientes nos comentários para responder a esta pergunta."
)

SYSTEM_PROMPT = """Você é o assistente analítico da Plataforma Sentinela, especializado em comentários do YouTube.
Responda à pergunta do usuário usando EXCLUSIVAMENTE os dados estruturados e os comentários fornecidos.

REGRAS
1. Se o contexto não for suficiente, responda exatamente: "{no_evidence}" Não adivinhe nem extrapole.
2. Não use conhecimento externo aos comentários fornecidos.
3. Responda em português do Brasil, de forma direta, em até 200 palavras.
4. Toda afirmação deve citar os comentários que a sustentam com o índice entre colchetes: [1], [2], [1, 3]. Nunca use intervalos como [1-3].
5. Use SEMPRE os colchetes ASCII "[" e "]" nas citações. Nunca use os colchetes de largura total 【 】.
6. Escreva em texto corrido, SEM formatação Markdown: nada de asteriscos (* ou **), sublinhados, cabeçalhos (#), listas com marcadores ou listas numeradas. Separe os assuntos em frases ou parágrafos.
7. Os metadados agregados servem para contextualizar proporções; não invente números que não estejam neles.

[METADADOS AGREGADOS]
{structured_context}

[COMENTÁRIOS DA AUDIÊNCIA]
{comments_context}"""


def build_structured_context(repo: AnalyticsRepository, youtube_id: str) -> str:
    """Resumo agregado do vídeo em texto — vem do Postgres, sem custo de LLM."""
    summary = repo.get_video_summary(youtube_id) or {}
    distribution = (repo.get_sentiment_distribution(youtube_id) or {}).get("distribution", {})
    intentions = (repo.get_intentions_distribution(youtube_id) or {}).get("intentions", [])
    products = (repo.get_top_products(youtube_id, limit=5, min_mentions=1) or {}).get("products", [])

    avg = summary.get("average_sentiment")
    linhas = [
        f"Total de comentários: {summary.get('total_comments', 0)} | "
        f"analisados: {summary.get('analyzed_comments', 0)} | "
        f"sentimento médio: {round(avg, 1) if avg is not None else 'n/d'}/5",
        "Distribuição: " + ", ".join(f"{nota}★ {distribution.get(nota, 0)}" for nota in "12345"),
    ]
    if intentions:
        linhas.append(
            "Intenções: " + ", ".join(f"{i['intent']} {i['count']}" for i in intentions[:8])
        )
    if products:
        linhas.append(
            "Produtos mais citados: "
            + ", ".join(
                f"{p['product_name']} ({p['count']}, média {round(p['average_sentiment'], 1)})"
                for p in products
            )
        )
    return "\n".join(linhas)


# Alguns modelos (ex: gpt-oss-120b) emitem colchetes de largura total em vez de ASCII;
# sem normalizar, a validação de citações e o parser do front-end não os reconhecem.
FULLWIDTH_BRACKETS = {
    "\u3010": "[", "\u3011": "]",   # 【 】
    "\u3014": "[", "\u3015": "]",   # 〔 〕
    "\uff3b": "[", "\uff3d": "]",   # ［ ］
}


def normalize_citation_brackets(answer: str) -> str:
    for original, ascii_bracket in FULLWIDTH_BRACKETS.items():
        answer = answer.replace(original, ascii_bracket)
    return answer


def strip_markdown(answer: str) -> str:
    """Remove marcação Markdown que o prompt proíbe mas o modelo às vezes emite.

    O front renderiza a resposta como texto (o parser de citações trabalha sobre
    ela), então `**negrito**` e marcadores de lista apareceriam literalmente.
    """
    answer = re.sub(r"\*\*(.+?)\*\*", r"\1", answer, flags=re.DOTALL)   # **negrito**
    answer = re.sub(r"__(.+?)__", r"\1", answer, flags=re.DOTALL)         # __negrito__
    answer = re.sub(r"^\s{0,3}#{1,6}\s*", "", answer, flags=re.MULTILINE)  # # cabeçalho
    answer = re.sub(r"(?m)^\s*[*+-]\s+", "", answer)                      # marcador no início da linha
    answer = re.sub(r"(?<=[\s.;:])[*+-]\s+(?=[A-ZÀ-Ú])", "", answer)       # marcador embutido no parágrafo
    return answer.replace("**", "")


def sanitize_answer(answer: str, max_index: int) -> str:
    """Normaliza colchetes, remove Markdown e descarta citações fora do intervalo."""
    return strip_invalid_citations(
        strip_markdown(normalize_citation_brackets(answer)).strip(),
        max_index,
    )


def strip_invalid_citations(answer: str, max_index: int) -> str:
    """Remove citações que apontam para índices inexistentes.

    O modelo ocasionalmente cita um [7] quando só há 5 fontes; deixar passar
    quebraria a resolução da citação no front-end.
    """
    def _fix(match):
        indices = [i.strip() for i in match.group(1).split(",")]
        validos = [i for i in indices if i.isdigit() and 1 <= int(i) <= max_index]
        return f"[{', '.join(validos)}]" if validos else ""

    limpo = re.sub(r"\[(\d+(?:\s*,\s*\d+)*)\]", _fix, answer)
    # Remover uma citação deixa espaço órfão antes da pontuação ("reclamam ." -> "reclamam.")
    limpo = re.sub(r"[ \t]+([.,;:!?])", r"\1", limpo)
    return re.sub(r"[ \t]{2,}", " ", limpo)


def ask_insight_use_case(
    db: Session,
    search_service,
    llm_service,
    youtube_id: str,
    req: AskRequest,
) -> AskResponse:
    """Responde a uma pergunta sobre os comentários de um vídeo, com citações.

    Não trata excepções do LLM: rate limit, timeout e falha de conexão sobem para
    o router, que as mapeia para o status HTTP adequado.
    """
    comments, distances, strategy_used = retrieve(
        db, search_service, youtube_id, req.question, req.strategy, req.filters
    )
    comments_context, used = build_context(comments)

    sources: List[SourceComment] = [
        SourceComment(
            index=i + 1,
            id=c.id,
            author=c.author,
            text=(c.text or "")[:MAX_COMMENT_CHARS],
            sentiment=c.sentiment,
            intent=c.intent,
            product_mentioned=c.product_mentioned,
            distance=distances.get(c.id),
        )
        for i, c in enumerate(used)
    ]

    if not used:
        # Sem evidência não se gasta chamada de LLM (a cota é partilhada com o worker_ai).
        return AskResponse(
            answer=NO_EVIDENCE,
            sources=[],
            strategy_used=strategy_used,
            comments_in_context=0,
            llm_called=False,
        )

    structured = build_structured_context(AnalyticsRepository(db), youtube_id)
    raw_answer = llm_service.answer(
        SYSTEM_PROMPT.format(
            no_evidence=NO_EVIDENCE,
            structured_context=structured,
            comments_context=comments_context,
        ),
        req.question,
    )

    return AskResponse(
        answer=sanitize_answer(raw_answer, len(used)),
        sources=sources,
        strategy_used=strategy_used,
        comments_in_context=len(used),
        llm_called=True,
    )
