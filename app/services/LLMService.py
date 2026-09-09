# app/services/LLMService.py
"""
Suporta dois providers via API compatível com OpenAI:
  - LLM_PROVIDER=groq   (default) → Groq cloud, modelo openai/gpt-oss-120b
  - LLM_PROVIDER=ollama           → Ollama local, modelo llama3.2 (sem limites de cota)

Para Ollama: instalar em https://ollama.com e executar `ollama pull <modelo>`.
"""

import os
import json
import re
from openai import OpenAI, RateLimitError, APIConnectionError, APITimeoutError

from app.schemas.LLMAnalysisSchema import CommentAnalysisResponse


# Excepção pública usada por ai_tasks para retry — independente do provider
class LLMRateLimitError(Exception):
    def __init__(self, message: str, retry_after_seconds: int = 300):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


# Aliases públicos para que routers e use cases mapeiem falhas de LLM sem
# importar o SDK da OpenAI directamente.
# Nota: APITimeoutError é subclasse de APIConnectionError — capture o timeout primeiro.
LLMTimeoutError = APITimeoutError
LLMConnectionError = APIConnectionError


class LLMService:
    def __init__(self):
        provider = os.getenv("LLM_PROVIDER", "groq").lower()

        if provider == "ollama":
            base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
            self.model = os.getenv("LLM_MODEL", "llama3.2")
            self.client = OpenAI(base_url=base_url, api_key="ollama")
            print(f"[LLMService] Provider: Ollama — {base_url} — modelo: {self.model}")
        else:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("A variável de ambiente GROQ_API_KEY não está configurada.")
            self.model = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
            self.client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=api_key,
            )
            print(f"[LLMService] Provider: Groq — modelo: {self.model}")

        # Modelo dedicado ao RAG do módulo de Insights. Permite usar um modelo
        # mais barato/rápido nas respostas do /ask sem mexer na análise por comentário.
        self.insights_model = os.getenv("LLM_INSIGHTS_MODEL") or self.model

    @staticmethod
    def _parse_retry_after(message: str, default: int = 300) -> int:
        """Extrai o tempo de espera da mensagem de rate limit do provider.

        Formato típico do Groq: "... please try again in 2m13.5s ...".
        Devolve `default` quando a mensagem não segue esse padrão.
        """
        match = re.search(r'try again in (?:(\d+)m)?(\d+(?:\.\d+)?)s', message)
        if not match:
            return default
        minutes = int(match.group(1) or 0)
        seconds = float(match.group(2))
        return int(minutes * 60 + seconds) + 5

    def answer(self, system_prompt: str, user_prompt: str,
               timeout: float = 30.0, temperature: float = 0.1) -> str:
        """Resposta em texto livre para o RAG do módulo de Insights.

        Ao contrário de `analyze_comment`, não devolve um default seguro em caso
        de erro: o chamador (use case/router) precisa distinguir rate limit,
        timeout e indisponibilidade para mapear ao status HTTP correto.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.insights_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                timeout=timeout,
            )
            return response.choices[0].message.content or ""
        except RateLimitError as e:
            raise LLMRateLimitError(str(e), retry_after_seconds=self._parse_retry_after(str(e)))
        # APITimeoutError e APIConnectionError propagam para o chamador tratar

    def analyze_comment(self, comment_text: str) -> CommentAnalysisResponse:
        system_instruction = (
            "És um analista de dados especialista em marketing de influência e e-commerce. "
            "Analisa o comentário fornecido por um utilizador num vídeo do YouTube. "
            "Responde ESTRITAMENTE num formato JSON válido, com as chaves exatas:\n"
            '- "sentiment": inteiro de 1 a 5 (1=muito negativo, 5=muito positivo).\n'
            '- "intent": string curta usando APENAS um destes valores: '
            '"Intencao_Compra", "Duvida", "Elogio", "Critica", "Comparacao", "Sugestao", "Informacao_Preco", "Informacao_Tecnica", "Descontentamento".\n'
            '- "product_mentioned": string com o nome COMPLETO e CANÔNICO do produto (ex: "Poco X8 Pro"), '
            "ou null se nenhum produto específico for mencionado. "
            "Usa sempre a capitalização oficial da marca. "
            "Nunca uses abreviações parciais nem minúsculas para nomes de produtos."
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": f"Comentário a analisar:\n'{comment_text}'"},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )

            raw = response.choices[0].message.content
            result_dict = json.loads(raw)
            return CommentAnalysisResponse(**result_dict)

        except APIConnectionError:
            # Ollama não acessível ou Groq com problema de rede — re-lança para retry do Celery
            raise

        except RateLimitError as e:
            # Extrai tempo de espera da mensagem do Groq e re-lança como excepção própria
            raise LLMRateLimitError(str(e), retry_after_seconds=self._parse_retry_after(str(e)))

        except Exception as e:
            print(f"[LLMService] Erro ao processar comentário: {e}")
            return CommentAnalysisResponse(sentiment=3, intent="Erro_IA", product_mentioned=None)
