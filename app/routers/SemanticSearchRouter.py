from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.services.SemanticSearchService import SemanticSearchService
from app.use_cases.SemanticSearch.execute_semantic_search import execute_search_use_case
from app.dependencies import get_search_service
from typing import Optional

router = APIRouter(
    prefix="/semantic-search",
    tags=["Busca Semântica"]
)

class SearchQuery(BaseModel):
    query: str
    video_id: Optional[str] = None 

@router.post("/semantic-search")
def run_semantic_search(
    request_data: SearchQuery,
    search_service: SemanticSearchService = Depends(get_search_service)
):
    """
    Endpoint para realizar a busca semântica.
    Recebe uma pergunta (query) e retorna os comentários mais relevantes.
    Pode filtrar opcionalmente por um 'video_id'.
    """
    try:
        resultados = execute_search_use_case(
            query=request_data.query,
            search_service=search_service,
            video_id_filter=request_data.video_id
        )
        return {
            "query": request_data.query,
            "video_id_filter": request_data.video_id,
            "results": resultados
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno: {e}")