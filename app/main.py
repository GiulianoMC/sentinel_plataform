import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.services.SemanticSearchService import SemanticSearchService
from app.dependencies import app_state

from app.database import engine
from app.models import VideoModel 

from app.routers import SemanticSearchRouter, IngestionRouter, VideoRouter, AnalyticsRouter, ReprocessRouter

@asynccontextmanager
async def lifespan(app: FastAPI):
    
    print("--- [API] A criar tabelas do banco de dados (se não existirem)... ---")
    VideoModel.Base.metadata.create_all(bind=engine)
    print("--- [API] Tabelas criadas com sucesso. ---")

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

app.include_router(SemanticSearchRouter.router)
app.include_router(IngestionRouter.router)
app.include_router(VideoRouter.router)
app.include_router(AnalyticsRouter.router)
app.include_router(ReprocessRouter.router)
