---
name: llm-provider
description: Sentinela usa Groq (Llama 3.3) para análise de comentários, não Gemini
metadata:
  type: project
---

A análise de comentários da Plataforma Sentinela é feita pela **Groq** (Llama 3.3 70B, free tier com JSON mode), não pelo Gemini. A migração aconteceu porque o Gemini free tier do usuário deu `limit: 0` em todos os modelos — ver [[api-keys-gotchas]].

- Service: [app/services/LLMService.py] — classe `LLMService` (substituiu `GeminiService`).
- Env vars: `GROQ_API_KEY` (obrigatória) e `LLM_MODEL` (default `llama-3.3-70b-versatile`, override possível para `llama-3.1-8b-instant` etc.).
- Dependência: `groq` no `requirements.txt`.
- Rate limit: `process_comments_with_ai` tem `rate_limit="10/m"` em [app/celery/ai_tasks.py] (compartilhado entre os 16 prefork workers).
- Falha de LLM grava `intent="Erro_IA"`; recuperar via `POST /reprocess/ai`.

Trocar para outro provedor OpenAI-compatible (OpenRouter, Cerebras, Mistral) é mexer só em `LLMService.py` — o restante do pipeline não depende do provedor.
