# app/services/GeminiService.py
import os
import json
import google.generativeai as genai
from app.schemas.LLMAnalysisSchema import CommentAnalysisResponse

class GeminiService:
    def __init__(self):
        # A chave de API deve estar no ficheiro .env ou no docker-compose.yml
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("A variável de ambiente GEMINI_API_KEY não está configurada.")
        
        genai.configure(api_key=api_key)
        
        # Modelo atualizado - gemini-2.0-flash é a versão mais recente
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    def analyze_comment(self, comment_text: str) -> CommentAnalysisResponse:
        system_instruction = """
        És um analista de dados especialista em marketing de influência e e-commerce.
        Analisa o comentário fornecido por um utilizador num vídeo do YouTube.
        Responde ESTRITAMENTE num formato JSON válido, com as chaves exatas: "sentiment" (inteiro), "intent" (string) e "product_mentioned" (string ou null).
        """
        
        prompt = f"{system_instruction}\n\nComentário a analisar:\n'{comment_text}'"

        try:
            # Pedimos ao Gemini para devolver a resposta obrigatoriamente como JSON
            response = self.model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                )
            )
            
            # Converte a string JSON devolvida pela IA num dicionário Python
            result_dict = json.loads(response.text)
            
            # Valida e devolve usando o nosso Schema Pydantic
            return CommentAnalysisResponse(**result_dict)
            
        except Exception as e:
            print(f"[GeminiService] Erro ao processar comentário: {e}")
            # Em caso de falha da IA, devolvemos valores padrão de segurança para não quebrar a base de dados
            return CommentAnalysisResponse(sentiment=3, intent="Erro_IA", product_mentioned=None)