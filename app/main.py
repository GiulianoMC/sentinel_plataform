from fastapi import FastAPI, HTTPException, Depends
from contextlib import asynccontextmanager
from app.services.SemanticSearchService import SemanticSearchService
from app.use_cases.SemanticSearch.execute_semantic_search import execute_search_use_case
from pydantic import BaseModel

lifespan_storage = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("--- Evento de arranque da API ---")
    service = SemanticSearchService()
    
    comentarios_base = [
        "A bateria deste telemóvel dura imenso, recomendo vivamente!",
        "O ecrã tem uma qualidade de imagem incrível, as cores são muito vivas.",
        "Qual é o período de garantia para este produto?",
        "O custo do frete para a minha região está demasiado alto.",
        "A autonomia da bateria é realmente um grande diferencial neste aparelho.",
        "A câmara tira fotografias fantásticas, mesmo com pouca luz."
    ]
    
    service.setup_collection("comentarios_produtos", comentarios_base)
    
    lifespan_storage['search_service'] = service
    
    yield 
    
    print("--- Evento de término da API ---")
    lifespan_storage.clear()

app = FastAPI(
    title="Plataforma Sentinela - Busca Semântica",
    lifespan=lifespan
)

def get_search_service() -> SemanticSearchService:
    """
    Função de dependência do FastAPI que fornece a instância
    do serviço aos endpoints que a requisitarem.
    """
    return lifespan_storage['search_service']

class SearchQuery(BaseModel):
    query: str

# --- Endpoints da API ---
@app.get("/")
def read_root():
    return {"status": "API de Busca Semântica está a funcionar"}

@app.post("/semantic-search")
def run_semantic_search(
    request_data: SearchQuery,
    search_service: SemanticSearchService = Depends(get_search_service)
):
    """
    Endpoint para realizar a busca semântica.
    Recebe uma pergunta (query) e retorna os comentários mais relevantes.
    """
    try:
        resultados = execute_search_use_case(
            query=request_data.query,
            search_service=search_service
        )
        return {
            "query": request_data.query,
            "results": resultados
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Captura outras exceções inesperadas
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno: {e}")
