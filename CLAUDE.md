# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

"Plataforma Sentinela" is a data engineering platform (Engineering TCC project) that ingests YouTube comments at scale and analyzes them with AI: semantic search via embeddings (ChromaDB) plus per-comment LLM analysis (Groq / Llama 3.3) for sentiment, intent, and product mentions. Codebase comments and docs are in Portuguese.

## Running the project

Everything runs via Docker Compose — there is no local Python entrypoint.

```bash
docker-compose up --build      # build + start all services
docker-compose up worker       # start a single service
docker-compose logs -f worker  # follow logs for a service
```

Services and ports:
- `api` — FastAPI, exposed on host **8001** (container 8000). Docs at http://localhost:8001/docs. (Note: README says 8000, but compose maps the API to 8001; 8000 is taken by ChromaDB.)
- `chromadb` — vector DB, host 8000.
- `postgres` — relational DB (`admin/admin`, db `sentinela`), host 5432.
- `rabbitmq` — Celery broker, AMQP 5672, management UI 15672.
- `worker` — Celery worker (consumes ingestion + AI tasks).
- `beat` — Celery beat scheduler (triggers the collector).

Required env vars (set in `.env`, passed through `docker-compose.yml`): `YOUTUBE_API_KEY`, `GROQ_API_KEY`. Optional: `LLM_MODEL` (default `llama-3.3-70b-versatile`). `DATABASE_URL`, `CHROMA_HOST`, `CHROMA_PORT` are set by compose.

There is **no test suite, linter, or migration runner wired up**. Although `alembic` is in requirements, tables are created at runtime via `VideoModel.Base.metadata.create_all` in the FastAPI `lifespan` ([app/main.py](app/main.py)) — schema changes to models take effect on container restart only for *new* tables/columns (no automatic ALTER).

## Architecture

The system has two entry paths that both funnel into the same async pipeline:

1. **Scheduled collection** — `beat` triggers `coletar_comentarios_youtube` every 60s ([app/celery/collector_tasks.py](app/celery/collector_tasks.py)). It reads all registered `Video` rows, calls the YouTube API for comments newer than `video.ultimo_comentario_verificado_em` (incremental cursor, paginated, timezone-normalized to UTC), and enqueues one `processar_novo_comentario` task per new comment.
2. **Manual ingestion** — `POST /ingest/comentario` enqueues a single `processar_novo_comentario` task directly ([app/use_cases/IngestionRouter/execute_ingestion.py](app/use_cases/IngestionRouter/execute_ingestion.py)).

### The processing pipeline (the core flow)

`processar_novo_comentario` ([app/celery/tasks.py](app/celery/tasks.py)) is the heart of the system and runs a deliberate 3-step ordering with compensation:
1. Persist the `Comment` to **PostgreSQL first** (source of truth).
2. Generate the embedding and index into **ChromaDB** (`comentarios_produtos` collection, metadata `{"video_id": ...}`).
3. Fan out a separate `process_comments_with_ai` task (Groq Llama).

If ChromaDB succeeds but Postgres failed, it compensates by deleting the Chroma entry. The AI task ([app/celery/ai_tasks.py](app/celery/ai_tasks.py)) is decoupled so a slow/failing LLM never blocks ingestion; it re-fetches the comment by id (with retry to handle the race where AI runs before the Postgres commit is visible) and writes back `sentiment`, `intent`, `product_mentioned`. The task carries `rate_limit="10/m"` to stay under the Groq free-tier RPM budget — shared across the worker's prefork processes.

### Layering convention

Routers → use cases → services/repositories. Routers ([app/routers/](app/routers/)) only handle HTTP/Pydantic and delegate. Business logic lives in [app/use_cases/](app/use_cases/). Two distinct data-access styles coexist:
- **Services** ([app/services/](app/services/)) wrap external systems (ChromaDB, Gemini) and are instantiated **once per worker process** as module-level globals to amortize model loading — `SemanticSearchService` loads the `paraphrase-multilingual-mpnet-base-v2` sentence-transformer at construction. Do not instantiate these per-request.
- **Repositories** ([app/repositories/](app/repositories/)) take a SQLAlchemy `Session` and do DB queries. `AnalyticsRepository` pushes all aggregation (COUNT/AVG/GROUP BY) into Postgres rather than loading rows.

### Two data stores, by design

- **PostgreSQL** is the source of truth and the analytics store. `Video` and `Comment` models in [app/models/VideoModel.py](app/models/VideoModel.py); the FK is on `Comment.youtube_id → videos.youtube_id` (the YouTube ID, not the surrogate PK).
- **ChromaDB** holds only embeddings for semantic search (`search()` in [app/services/SemanticSearchService.py](app/services/SemanticSearchService.py), cosine distance, results filtered by a `threshold`; lower distance = more relevant).

`youtube_id` is the canonical identifier threaded through the whole system (API requests, Chroma metadata, analytics filters) — prefer it over the integer PK when adding features.

### FastAPI dependency injection

The shared `SemanticSearchService` for the API process lives in `app_state` ([app/dependencies.py](app/dependencies.py)), populated in `lifespan` and injected via `get_search_service`. DB sessions are injected per-request via `get_db` ([app/database.py](app/database.py)).

## Notes for changes

- Analytics is exposed via [app/routers/AnalyticsRouter.py](app/routers/AnalyticsRouter.py) (prefix `/analytics`): `GET /{youtube_id}/summary`, `/intentions`, `/products` (query params `limit`, `min_mentions`), and `/sentiment`. Each instantiates `AnalyticsRepository(db)` and returns 404 when the repo returns `None` (video not found). These read-only endpoints are what the front-end consumes.
- CORS is configured in [app/main.py](app/main.py) via `CORS_ORIGINS` env var (comma-separated; defaults to `*`). Credentials are only allowed when explicit origins are set, since wildcard + credentials is blocked by browsers.
- LLM output is coerced into the `CommentAnalysisResponse` Pydantic schema; on any failure `LLMService.analyze_comment` ([app/services/LLMService.py](app/services/LLMService.py), Groq + Llama 3.3 with JSON mode) returns a safe default (`sentiment=3, intent="Erro_IA"`) rather than raising, so bad AI responses never corrupt the DB. To recover those rows after fixing the LLM, call `POST /reprocess/ai` ([app/routers/ReprocessRouter.py](app/routers/ReprocessRouter.py)) — by default it re-enqueues only the `Erro_IA` ones.
- Sentiment is an integer scale 1–5; `intent` and `product_mentioned` are free-form strings from the LLM.
- The collector and `register_video` both degrade gracefully when `YOUTUBE_API_KEY` is missing (log a warning, skip the API call).
