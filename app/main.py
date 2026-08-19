import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from app.services.SemanticSearchService import SemanticSearchService
from app.dependencies import app_state
from app.core.rate_limiter import limiter

from app.database import engine, Base
from app.models import VideoModel, UserModel

from app.routers import (
    SemanticSearchRouter, IngestionRouter, VideoRouter, 
    AnalyticsRouter, ReprocessRouter, auth_router, AdminRouter
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    
    print("--- [API] A criar tabelas do banco de dados (se não existirem)... ---")
    Base.metadata.create_all(bind=engine)
    print("--- [API] Tabelas criadas com sucesso. ---")

    # create_all não altera tabelas já existentes. Se o banco é de antes da
    # autenticação, a coluna videos.user_id não existe e todas as queries com
    # Video.user_id quebrariam com "column does not exist". Falhe cedo e
    # instrua a aplicar as migrações.
    from sqlalchemy import inspect
    inspector = inspect(engine)
    if "videos" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("videos")}
        if "user_id" not in columns:
            raise RuntimeError(
                "O banco de dados existente não possui a coluna 'videos.user_id'. "
                "Aplique as migrações: docker-compose run --rm api alembic upgrade head"
            )

    service = SemanticSearchService()
    
    print("--- [API] Assegurando que a coleção existe no ChromaDB (sem popular)... ---")
    service.setup_collection("comentarios_produtos", documents=[]) 
    
    app_state['search_service'] = service
    yield 
    
    app_state.clear()

app = FastAPI(
    title="Platrforma Sentinela - Busca Semântica",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: JSONResponse(
    status_code=429,
    content={"detail": "Rate limit exceeded. Tente novamente mais tarde."}
))

# CORS para permitir que o front-end (browser) consuma a API.
# Defina CORS_ORIGINS no .env (lista separada por vírgula) em produção; "*" no desenvolvimento.
_cors_origins = os.environ.get("CORS_ORIGINS", "*")
allow_all = _cors_origins.strip() == "*"
allow_origins = ["*"] if allow_all else [o.strip() for o in _cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    # Wildcard + credenciais é bloqueado pelos browsers; só habilita credenciais com origens explícitas.
    allow_credentials=not allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(SemanticSearchRouter.router)
app.include_router(IngestionRouter.router)
app.include_router(VideoRouter.router)
app.include_router(AnalyticsRouter.router)
app.include_router(ReprocessRouter.router)
app.include_router(AdminRouter.router)
