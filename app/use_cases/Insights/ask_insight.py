# app/use_cases/Insights/ask_insight.py
"""Pipeline RAG: retrieval -> contexto (agregados + comentários) -> LLM com citações.

O escopo é um `AskScope`: um vídeo, ou todos os vídeos de um canal. No canal, o
prompt ganha rótulos por vídeo (V1, V2, ...) para a resposta poder dizer de que
vídeo vem cada evidência e responder a perguntas comparativas ("qual vídeo teve
a pior recepção?") a partir dos metadados por vídeo.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from sqlalchemy.orm import Session

from app.repositories.AnalyticsRepository import AnalyticsRepository
from app.repositories.InsightsRepository import InsightsRepository
from app.schemas.InsightsSchema import AskRequest, AskResponse, SourceComment
from app.use_cases.Insights.retrieval import MAX_COMMENT_CHARS, build_context, retrieve

NO_EVIDENCE = (
    "Não encontrei evidências suficientes nos comentários para responder a esta pergunta."
)

# Quantos vídeos entram na lista por vídeo dos metadados do canal (os mais comentados);
# vídeos fora do topo que aparecerem nos comentários são acrescentados para a legenda fechar.
MAX_VIDEOS_IN_METADATA = 15


@dataclass
class AskScope:
    """Um vídeo (`video_ids` com um item) ou um canal (todos os vídeos do utilizador nele)."""
    video_ids: List[str]
    channel_id: Optional[str] = None
    user_id: Optional[int] = None
    # Preenchido internamente no escopo de canal: {youtube_id: "V1"}
    labels: Dict[str, str] = field(default_factory=dict)

    @property
    def is_channel(self) -> bool:
        return self.channel_id is not None

    @classmethod
    def coerce(cls, value: Union[str, "AskScope"]) -> "AskScope":
        return value if isinstance(value, AskScope) else cls(video_ids=[value])


SYSTEM_PROMPT = """Você é o assistente analítico da Plataforma Sentinela, especializado em comentários do YouTube.
Responda à pergunta do usuário usando EXCLUSIVAMENTE os dados estruturados e os comentários fornecidos.

REGRAS
1. Se o contexto não for suficiente, responda exatamente: "{no_evidence}" Não adivinhe nem extrapole.
2. Não use conhecimento externo aos comentários fornecidos.
3. Responda em português do Brasil, de forma direta, em até 200 palavras.
4. Toda afirmação deve citar os comentários que a sustentam com o índice entre colchetes: [1], [2], [1, 3]. Nunca use intervalos como [1-3].
5. Use SEMPRE os colchetes ASCII "[" e "]" nas citações. Nunca use os colchetes de largura total 【 】.
6. Escreva em texto corrido, SEM formatação Markdown: nada de asteriscos (* ou **), sublinhados, cabeçalhos (#), listas com marcadores ou listas numeradas. Separe os assuntos em frases ou parágrafos.
7. Os metadados agregados servem para contextualizar proporções; não invente números que não estejam neles.{scope_rules}

[METADADOS AGREGADOS]
{structured_context}

[COMENTÁRIOS DA AUDIÊNCIA]
{comments_context}"""

CHANNEL_RULES = """
8. O contexto cobre VÁRIOS vídeos de um canal. Cada vídeo tem um rótulo (V1, V2, ...) que aparece na lista de vídeos dos metadados e no início de cada comentário (vídeo=V1). Quando a evidência vier de um vídeo específico, diga de qual vídeo é usando o TÍTULO do vídeo, nunca o rótulo.
9. Para perguntas que comparam vídeos (qual teve pior recepção, onde um produto é mais criticado), use a lista de vídeos dos metadados e cite os comentários que ilustram a diferença."""


def _summary_lines(summary: dict, distribution: dict, intentions: list, products: list) -> List[str]:
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
    return linhas


def build_structured_context(repo: AnalyticsRepository, youtube_id: str) -> str:
    """Resumo agregado do vídeo em texto — vem do Postgres, sem custo de LLM."""
    summary = repo.get_video_summary(youtube_id) or {}
    distribution = (repo.get_sentiment_distribution(youtube_id) or {}).get("distribution", {})
    intentions = (repo.get_intentions_distribution(youtube_id) or {}).get("intentions", [])
    products = (repo.get_top_products(youtube_id, limit=5, min_mentions=1) or {}).get("products", [])
    return "\n".join(_summary_lines(summary, distribution, intentions, products))


def channel_video_rows(repo: AnalyticsRepository, scope: AskScope) -> List[dict]:
    """Vídeos do canal do mais para o menos comentado; define a ordem dos rótulos V1, V2, ..."""
    overview = repo.get_overview(scope.user_id, channel_id=scope.channel_id)
    rows = [v for v in overview["videos"] if v["youtube_id"] in set(scope.video_ids)]
    # Desempate determinístico pelo id: created_at pode ser None em fixtures/legado.
    rows.sort(key=lambda v: (-v["total_comments"], v["youtube_id"]))
    return rows


def build_channel_structured_context(
    repo: AnalyticsRepository, scope: AskScope, video_rows: List[dict], used_video_ids: set
) -> str:
    """Agregados do canal + uma linha por vídeo (rótulo, título, analisados, média).

    A lista por vídeo é o que permite perguntas comparativas sem gastar contexto
    de comentários. Entram os MAX_VIDEOS_IN_METADATA mais comentados e qualquer
    outro que tenha comentários no prompt, para nenhum rótulo ficar sem legenda.
    """
    summary = repo.get_channel_summary(scope.channel_id, scope.user_id) or {}
    distribution = (repo.get_channel_sentiment_distribution(scope.channel_id, scope.user_id) or {}).get("distribution", {})
    intentions = (repo.get_channel_intentions(scope.channel_id, scope.user_id) or {}).get("intentions", [])
    products = (repo.get_channel_top_products(scope.channel_id, scope.user_id, limit=5, min_mentions=1) or {}).get("products", [])

    linhas = [
        f"Canal: {summary.get('channel_title') or scope.channel_id} | vídeos: {summary.get('total_videos', len(scope.video_ids))}",
        *_summary_lines(summary, distribution, intentions, products),
    ]

    listed = [
        v for i, v in enumerate(video_rows)
        if i < MAX_VIDEOS_IN_METADATA or v["youtube_id"] in used_video_ids
    ]
    if listed:
        linhas.append("Vídeos do canal (rótulo: título | comentários analisados | sentimento médio):")
        for v in listed:
            avg = v["average_sentiment"]
            linhas.append(
                f"  {scope.labels[v['youtube_id']]}: \"{v['titulo']}\" | {v['analyzed_comments']} analisados | "
                f"média {round(avg, 1) if avg is not None else 'n/d'}/5"
            )
    return "\n".join(linhas)


# Alguns modelos (ex: gpt-oss-120b) emitem colchetes de largura total em vez de ASCII;
# sem normalizar, a validação de citações e o parser do front-end não os reconhecem.
FULLWIDTH_BRACKETS = {
    "【": "[", "】": "]",   # 【 】
    "〔": "[", "〕": "]",   # 〔 〕
    "［": "[", "］": "]",   # ［ ］
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
    scope: Union[str, AskScope],
    req: AskRequest,
) -> AskResponse:
    """Responde a uma pergunta sobre os comentários de um vídeo ou de um canal, com citações.

    `scope` aceita um youtube_id (compatível com o worker de cards) ou um AskScope.
    Não trata excepções do LLM: rate limit, timeout e falha de conexão sobem para
    o router, que as mapeia para o status HTTP adequado.
    """
    scope = AskScope.coerce(scope)
    analytics = AnalyticsRepository(db)

    video_rows: List[dict] = []
    if scope.is_channel:
        video_rows = channel_video_rows(analytics, scope)
        scope.labels = {v["youtube_id"]: f"V{i + 1}" for i, v in enumerate(video_rows)}

    comments, distances, strategy_used = retrieve(
        db, search_service, scope.video_ids, req.question, req.strategy, req.filters
    )
    comments_context, used = build_context(comments, scope.labels or None)

    titles = InsightsRepository(db).get_video_titles(c.youtube_id for c in used)
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
            youtube_id=c.youtube_id,
            video_title=titles.get(c.youtube_id),
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

    if scope.is_channel:
        structured = build_channel_structured_context(
            analytics, scope, video_rows, {c.youtube_id for c in used}
        )
        scope_rules = CHANNEL_RULES
    else:
        structured = build_structured_context(analytics, scope.video_ids[0])
        scope_rules = ""

    raw_answer = llm_service.answer(
        SYSTEM_PROMPT.format(
            no_evidence=NO_EVIDENCE,
            scope_rules=scope_rules,
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
