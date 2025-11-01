from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.SemanticSearchService import SemanticSearchService
from app.repositories.CommentRepository import get_base_comments
from app.dependencies import app_state

# Importe os DOIS routers
from app.routers import SemanticSearchRouter, IngestionRouter

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Função de lifespan para carregar o modelo e a coleção
    na inicialização da API.
    """
    print("--- [API] Iniciando lifespan... ---")
    service = SemanticSearchService()
    comentarios_base = get_base_comments()
    
    # Nome da coleção que será usada em todo o sistema
    collection_name = "comentarios_produtos"
    
    service.setup_collection(collection_name, comentarios_base)
    
    app_state['search_service'] = service
    app_state['collection_name'] = collection_name # Guardar o nome da coleção
    
    print(f"--- [API] Serviço de busca e coleção '{collection_name}' carregados. ---")
    yield 
    
    print("--- [API] Encerrando lifespan... ---")
    app_state.clear()

# Inicializa a aplicação FastAPI
app = FastAPI(
    title="Plataforma Sentinela - Busca Semântica",
    lifespan=lifespan
)

# Registe os DOIS routers
print("--- [API] Registando routers... ---")
app.include_router(SemanticSearchRouter.router)
app.include_router(IngestionRouter.router)
print("--- [API] Routers registados com sucesso. ---")