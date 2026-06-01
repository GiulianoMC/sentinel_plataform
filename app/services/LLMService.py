# app/services/LLMService.py
"""
Serviço de análise de comentários via LLM (Groq).

Substitui o GeminiService — o Gemini free tier ficou inviável (limit: 0).
A Groq oferece os modelos Llama 3.x grátis com cota generosa e JSON mode,
e a API é praticamente igual à do OpenAI, então a migração mantém o mesmo
contrato (devolve um CommentAnalysisResponse).
"""

import os
import json
from groq import Groq

from app.schemas.LLMAnalysisSchema import CommentAnalysisResponse


class LLMService:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("A variável de ambiente GROQ_API_KEY não está configurada.")

        # Modelo configurável via env (ajuste se a Groq mover/depreciar):
        # - llama-3.3-70b-versatile  -> melhor qualidade (default)
        # - llama-3.1-8b-instant     -> mais rápido e barato em tokens
        self.model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        self.client = Groq(api_key=api_key)

    def analyze_comment(self, comment_text: str) -> CommentAnalysisResponse:
        # JSON mode da Groq exige a palavra "JSON" no prompt; já está no system_instruction.
        system_instruction = (
            "És um analista de dados especialista em marketing de influência e e-commerce. "
            "Analisa o comentário fornecido por um utilizador num vídeo do YouTube. "
            "Responde ESTRITAMENTE num formato JSON válido, com as chaves exatas:\n"
            '- "sentiment": inteiro de 1 a 5 (1=muito negativo, 5=muito positivo).\n'
            '- "intent": string curta usando APENAS um destes valores: '
            '"Intencao_Compra", "Duvida", "Elogio", "Critica", "Comparacao", "Sugestao", "Informacao_Preco", "Informacao_Tecnica", "Descontentamento".\n'
            '- "product_mentioned": string com o nome COMPLETO e CANÔNICO do produto (ex: "Poco X8 Pro", nunca apenas "X8 Pro" ou "x8 pro"), '
            "ou null se nenhum produto específico for mencionado. "
            "Usa sempre a capitalização oficial da marca (ex: 'iPhone 16 Pro Max', 'Samsung Galaxy S25', 'Poco X8 Pro'). "
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

        except Exception as e:
            print(f"[LLMService] Erro ao processar comentário: {e}")
            # Mesma estratégia de safe-default do GeminiService anterior:
            # nunca quebra o pipeline; comentário fica marcado como Erro_IA até reprocessar.
            return CommentAnalysisResponse(sentiment=3, intent="Erro_IA", product_mentioned=None)
