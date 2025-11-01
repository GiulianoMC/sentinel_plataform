from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.SemanticSearchService import SemanticSearchService
from app.dependencies import app_state

from app.routers import SemanticSearchRouter, IngestionRouter

@asynccontextmanager
async def lifespan(app: FastAPI):

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

app.include_router(SemanticSearchRouter.router)
app.include_router(IngestionRouter.router)
