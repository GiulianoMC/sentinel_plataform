---
name: api-keys-gotchas
description: Pitfalls with YOUTUBE_API_KEY and GEMINI_API_KEY when running the platform
metadata:
  type: project
---

Ao rodar a Plataforma Sentinela, duas armadilhas de chave de API já custaram tempo:

1. **YouTube** — uma key pode buscar o *título* do vídeo mas falhar em `commentThreads.list` com `403 "Requests to this API method ... are blocked"`. Não é "comentários desativados" (o coletor loga isso, mas é enganoso): é **restrição da API key** no Google Cloud Console (API restrictions sem "YouTube Data API v3", ou Application restriction "HTTP referrers" que bloqueia chamadas de servidor). Corrigir na console; não precisa rebuild.

2. **Gemini** — `429 ... limit: 0, model: gemini-2.0-flash` significa que a key tem **zero** de free tier para o modelo (key criada em projeto GCP sem free tier, ou modelo sem free tier na região). Gere a key via Google AI Studio, ou troque o modelo em [GeminiService.py], ou ative billing. O `GeminiService` engole o erro e grava `intent="Erro_IA"` no Postgres — então falhas de quota viram dado permanente até reprocessar.

**Trocar chave no `.env` exige recriar os containers** (não basta `restart`, que reusa o env antigo): `sudo docker compose up -d --force-recreate worker beat api`. As keys são lidas no nível de módulo na inicialização do processo.

Para recuperar comentários marcados como `Erro_IA`: `POST /reprocess/ai` (re-enfileira a análise). O worker tem `rate_limit="10/m"` em `process_comments_with_ai` para não estourar a quota.
