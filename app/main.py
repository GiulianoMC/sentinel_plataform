import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from app.services.SemanticSearchService import SemanticSearchService
from app.dependencies import app_state
from app.core.rate_limiter import limiter

from app.database import engine

from app.routers import (
    SemanticSearchRouter, IngestionRouter, VideoRouter, 
    AnalyticsRouter, ReprocessRouter, auth_router, AdminRouter
)

def _ensure_migrations() -> None:
    """Aplica as migrações Alembic antes de servir qualquer requisição.

    Alembic é a única fonte de verdade do schema. Bancos legados criados via
    create_all não possuem a tabela alembic_version, mas o schema gerado por
    create_all corresponde ao head das migrações; nesse caso, marca-se o
    baseline (stamp head) para o upgrade não tentar recriar tabelas existentes.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")

    inspector = inspect(engine)
    if not inspector.has_table("alembic_version") and inspector.get_table_names():
        command.stamp(cfg, "head")
        print("--- [API] Banco legado (create_all) marcado como baseline alembic. ---")

    command.upgrade(cfg, "head")
    print("--- [API] Migrações aplicadas (alembic upgrade head). ---")

@asynccontextmanager
async def lifespan(app: FastAPI):

    _ensure_migrations()

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
