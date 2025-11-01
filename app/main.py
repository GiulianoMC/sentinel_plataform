from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.SemanticSearchService import SemanticSearchService
from app.repositories.CommentRepository import get_base_comments
from app.dependencies import app_state
from app.routers import SemanticSearchRouter

@asynccontextmanager
async def lifespan(app: FastAPI):

    service = SemanticSearchService()
    comentarios_base = get_base_comments()
    service.setup_collection("comentarios_produtos", comentarios_base)
    
    app_state['search_service'] = service    
    yield 
    
    app_state.clear()

app = FastAPI(
    title="Plataforma Sentinela - Busca Semântica",
    lifespan=lifespan
)

app.include_router(SemanticSearchRouter.router)

