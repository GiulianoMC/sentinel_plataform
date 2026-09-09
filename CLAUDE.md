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
- `worker` — Celery worker (queue `ingestion`: Postgres + embeddings).
- `worker_ai` — Celery worker (queue `ai`: LLM calls only; no Chroma, no sentence-transformer).
- `beat` — Celery beat scheduler (triggers the collector).

Required env vars (set in `.env`, passed through `docker-compose.yml`; see `.env.example`): `YOUTUBE_API_KEY`, `GROQ_API_KEY`. Optional: `LLM_MODEL` (default `openai/gpt-oss-120b`), `LLM_PROVIDER` (`groq` default, or `ollama`), `LLM_INSIGHTS_MODEL` (model used only by the Insights RAG; empty = `LLM_MODEL`). `DATABASE_URL`, `CHROMA_HOST`, `CHROMA_PORT` are set by compose.

Celery is configured in [app/celery/celery_app.py](app/celery/celery_app.py): broker/backend point to RabbitMQ, and the beat schedule registers `coletar_comentarios_youtube` at a 60-second interval.

Migrations are versioned via **Alembic** (base revision `000` in [alembic/versions](alembic/versions), head `003`). At startup, the FastAPI `lifespan` ([app/main.py](app/main.py)) runs `alembic upgrade head` automatically, so `docker-compose up --build` on a brand-new database works with no manual step (Alembic creates the whole schema). For legacy databases that were created by `create_all` (no `alembic_version` table), the lifespan stamps `head` as the baseline before upgrading, since `create_all` produced a schema equivalent to the current migrations. There is **no linter wired up**, but there **is** a pytest suite in `tests/` (run with `pytest` — SQLite by default, or set `TEST_DATABASE_URL` for PostgreSQL). Manual migration commands (`docker-compose run --rm api alembic upgrade head`) still work as a fallback; the `alembic.ini` and `alembic/` directory are copied into the API image by the Dockerfile.

## Architecture

The system has two entry paths that both funnel into the same async pipeline:

1. **Scheduled collection** — `beat` triggers `coletar_comentarios_youtube` every 60s ([app/celery/collector_tasks.py](app/celery/collector_tasks.py)). It reads all registered `Video` rows, calls the YouTube API for comments newer than `video.ultimo_comentario_verificado_em` (incremental cursor, paginated, timezone-normalized to UTC), and enqueues one `processar_novo_comentario` task per new comment.
2. **Manual ingestion** — `POST /ingest/comentario` enqueues a single `processar_novo_comentario` task directly ([app/use_cases/IngestionRouter/execute_ingestion.py](app/use_cases/IngestionRouter/execute_ingestion.py)).

### The processing pipeline (the core flow)

`processar_novo_comentario` ([app/celery/tasks.py](app/celery/tasks.py)) is the heart of the system and runs a deliberate ordering with compensation:
1. Verify the `Video` exists (aborts otherwise).
2. Persist the `Comment` to **PostgreSQL first** (source of truth) — idempotent: if the id already exists (retry/duplicate), it skips the INSERT.
3. Generate the embedding and index into **ChromaDB** (`comentarios_produtos` collection, metadata `{"video_id": ...}`) via `upsert` (idempotent).
4. Fan out a separate `process_comments_with_ai` task (Groq Llama).

If ChromaDB succeeds but Postgres failed, it compensates by deleting the Chroma entry. The AI task ([app/celery/ai_tasks.py](app/celery/ai_tasks.py)) is decoupled so a slow/failing LLM never blocks ingestion; it re-fetches the comment by id (with retry to handle the race where AI runs before the Postgres commit is visible) and writes back `sentiment`, `intent`, `product_mentioned`. The task has no fixed `rate_limit`; instead it parses Groq's `RateLimitError` message, waits `retry_after` (via `LLMRateLimitError`) and retries up to 20 times with backoff.

### The Insights module (`/insights`)

Retrieve-then-join: `Comment.id` (Postgres PK) and the Chroma document id are the **same string**, so the vector search returns ids, the ids are looked up in Postgres, and the rows are reordered in Python to preserve Chroma's relevance order (`InsightsRepository.get_comments_by_ids`). Endpoints in [app/routers/InsightsRouter.py](app/routers/InsightsRouter.py), all scoped by ownership (404 otherwise) via `get_owned_video` ([app/utils/video_utils.py](app/utils/video_utils.py)):

- `GET /{youtube_id}/search` — hybrid search (semantic order + structured fields).
- `POST /{youtube_id}/ask` — RAG with citations; rate-limited to 10/min because it shares the Groq quota with `worker_ai`.
- `GET /{youtube_id}/suggested-questions` — deterministic, no LLM; each suggestion carries the `strategy`/`filters` that make it work in `/ask`.
- `GET /{youtube_id}/cards` and `POST /{youtube_id}/cards/generate` — LLM-generated cards read from a Postgres cache (`video_insights`).
- `POST /{youtube_id}/comments/by-ids` — resolves a list of comment ids into full comments, in the order requested (max 100). Backs the evidence display for cards, which only store `evidence_ids`. The lookup is scoped to the path's video, so ids from another video are dropped even when the caller owns both.

**Retrieval strategies** ([app/use_cases/Insights/retrieval.py](app/use_cases/Insights/retrieval.py)): `semantic` (Chroma), `sample` (stratified-by-sentiment sample in Postgres, for generic questions with no semantic anchor), `auto` (semantic, falling back to sample below `MIN_EVIDENCE`). `search_service=None` forces `sample` — that is how `worker_ai` generates cards without loading the sentence-transformer. Context is capped by `MAX_COMMENT_CHARS`/`MAX_CONTEXT_CHARS`; with no evidence the LLM is skipped entirely (`llm_called=False`). Every answer passes through `sanitize_answer` ([ask_insight.py](app/use_cases/Insights/ask_insight.py)): it normalizes full-width brackets (`gpt-oss-120b` emits `【6】` instead of `[6]`, which would bypass citation validation and the front-end parser), strips Markdown the prompt forbids but models still emit, and drops citations pointing outside the source range.

**Chroma metadata**: `{"video_id", "sentiment", "intent", "product"}` — written back by `sync_chroma_metadata` ([app/celery/tasks.py](app/celery/tasks.py)) after each AI analysis, so vector search can filter by sentiment/intent/product. Chroma 0.4.15 rejects `None`, hence the `"none"` sentinel; `product` is lowercased/trimmed to match `AnalyticsRepository.get_top_products`. `collection.update` on a missing id is a silent no-op — `POST /reprocess/chroma-metadata` backfills. `processar_novo_comentario` rebuilds metadata from the stored analysis so an ingestion retry never erases it.

**Cards cache** (`video_insights`, migration `003`): one row per `(youtube_id, kind)`. A read marks the four kinds `pending` and commits *before* enqueueing `generate_video_insights` — that is the lock against concurrent generations, expiring after 10 minutes. Regeneration only happens when `is_stale` (more than +20% analyzed comments, floor of +10) and at least 5 analyzed comments exist.

### Layering convention

Routers → use cases → services/repositories. Routers ([app/routers/](app/routers/)) only handle HTTP/Pydantic and delegate. Business logic lives in [app/use_cases/](app/use_cases/). Two distinct data-access styles coexist:
- **Services** ([app/services/](app/services/)) wrap external systems (ChromaDB, Groq) and are instantiated **once per worker process** as module-level globals to amortize model loading — `SemanticSearchService` loads the `paraphrase-multilingual-mpnet-base-v2` sentence-transformer at construction. Do not instantiate these per-request.
- **Repositories** ([app/repositories/](app/repositories/)) take a SQLAlchemy `Session` and do DB queries. `AnalyticsRepository` pushes all aggregation (COUNT/AVG/GROUP BY) into Postgres rather than loading rows. `CommentRepository` ([app/repositories/CommentRepository.py](app/repositories/CommentRepository.py)) is a test-data helper with hardcoded Portuguese mock comments — not used in the live pipeline.
- **Schemas** ([app/schemas/](app/schemas/)) hold Pydantic models for API responses: `AnalyticsSchema.py` (summary, intentions, products, sentiment distribution) and `LLMAnalysisSchema.py` (`CommentAnalysisResponse` with `sentiment`, `intent`, `product_mentioned`).

### Two data stores, by design

- **PostgreSQL** is the source of truth and the analytics store. `Video` and `Comment` models in [app/models/VideoModel.py](app/models/VideoModel.py); the FK is on `Comment.youtube_id → videos.youtube_id` (the YouTube ID, not the surrogate PK).
- **ChromaDB** holds only embeddings for semantic search (`search()` in [app/services/SemanticSearchService.py](app/services/SemanticSearchService.py), cosine distance, results filtered by a `threshold`; lower distance = more relevant).

`youtube_id` is the canonical identifier threaded through the whole system (API requests, Chroma metadata, analytics filters) — prefer it over the integer PK when adding features.

### FastAPI dependency injection

The shared `SemanticSearchService` for the API process lives in `app_state` ([app/dependencies.py](app/dependencies.py)), populated in `lifespan` and injected via `get_search_service`. DB sessions are injected per-request via `get_db` ([app/database.py](app/database.py)).

## Notes for changes

- Analytics is exposed via [app/routers/AnalyticsRouter.py](app/routers/AnalyticsRouter.py) (prefix `/analytics`): `GET /{youtube_id}/summary`, `/intentions`, `/products` (query params `limit`, `min_mentions`), and `/sentiment`. Each instantiates `AnalyticsRepository(db)` and returns 404 when the repo returns `None` (video not found). These read-only endpoints are what the front-end consumes.
- CORS is configured in [app/main.py](app/main.py) via `CORS_ORIGINS` env var (comma-separated; defaults to `*`). Credentials are only allowed when explicit origins are set, since wildcard + credentials is blocked by browsers. `expose_headers=["Retry-After"]` is required for the front-end to read the rate-limit countdown — browsers hide non-safelisted response headers from cross-origin JS. Rate limiting returns **429** with `Retry-After` (the slowapi window, via `_rate_limit_handler`); an exhausted LLM quota returns **503** with `Retry-After` (seconds parsed from the provider message).
- LLM output is coerced into the `CommentAnalysisResponse` Pydantic schema; on any failure `LLMService.analyze_comment` ([app/services/LLMService.py](app/services/LLMService.py), Groq + Llama 3.3 with JSON mode) returns a safe default (`sentiment=3, intent="Erro_IA"`) rather than raising, so bad AI responses never corrupt the DB. To recover those rows after fixing the LLM, call `POST /reprocess/ai` ([app/routers/ReprocessRouter.py](app/routers/ReprocessRouter.py)) — by default it re-enqueues only the `Erro_IA` ones.
- Sentiment is an integer scale 1–5; `intent` and `product_mentioned` are free-form strings from the LLM.
- The collector and `register_video` both degrade gracefully when `YOUTUBE_API_KEY` is missing (log a warning, skip the API call).
- Tests that need the *real* `SemanticSearchService`, `LLMService` or `app.celery.*` modules must load them via `tests/helpers.py` (`load_real_module`): `tests/conftest.py` replaces those modules in `sys.modules` with mocks so the API can be imported without chromadb/sentence-transformers. `make_celery_stub()` makes `@celery.task` return the real function so tasks can be called directly.
- `chromadb` is pinned to `0.4.15` in `requirements.txt` — the client API changed significantly in 0.5.x. Do not upgrade without auditing `SemanticSearchService` against the new API.
