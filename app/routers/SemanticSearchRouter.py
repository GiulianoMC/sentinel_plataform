from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.services.SemanticSearchService import SemanticSearchService
from app.use_cases.SemanticSearch.execute_semantic_search import execute_search_use_case
from app.dependencies import get_search_service
from typing import Optional, List, Dict, Any

router = APIRouter(
    prefix="/semantic-search",
    tags=["Busca Semântica"]
)

class SearchQuery(BaseModel):
    query: str
    youtube_id: Optional[str] = None
    num_results: int = 10
    threshold: float = 0.6

class SearchResult(BaseModel):
    documento: str
    distancia: float
    metadados: Optional[Dict[str, Any]]

@router.post("/semantic-search", response_model=List[SearchResult])
def run_semantic_search(
    request_data: SearchQuery,
    search_service: SemanticSearchService = Depends(get_search_service)
):
    """
    Endpoint para realizar a busca semântica.
    Recebe uma pergunta (query) e retorna os comentários mais relevantes.
    - 'youtube_id': O ID do vídeo no YouTube (ex: vPsayRIEJmE).
    - 'num_results': O número máximo de comentários a verificar.
    - 'threshold': O limite de relevância (distância). Menor é melhor. (ex: 0.6)
    """
    try:
        resultados = execute_search_use_case(
            query=request_data.query,
            search_service=search_service,
            video_id_filter=request_data.youtube_id,
            num_results=request_data.num_results,
            threshold=request_data.threshold
        )
        return resultados
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno: {e}")