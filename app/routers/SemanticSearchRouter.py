from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.services.SemanticSearchService import SemanticSearchService
from app.use_cases.SemanticSearch.execute_semantic_search import execute_search_use_case
from app.dependencies import get_search_service, get_current_active_user
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.UserModel import User
from app.models.VideoModel import Video
from app.utils.video_utils import get_user_video_ids

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
    search_service: SemanticSearchService = Depends(get_search_service),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Endpoint para realizar a busca semântica.
    Recebe uma pergunta (query) e retorna os comentários mais relevantes.
    - 'youtube_id': O ID do vídeo no YouTube (ex: vPsayRIEJmE).
    - 'num_results': O número máximo de comentários a verificar.
    - 'threshold': O limite de relevância (distância). Menor é melhor. (ex: 0.6)
    """
    # Se youtube_id for fornecido, verifica se pertence ao usuário
    if request_data.youtube_id:
        video = db.query(Video).filter(Video.youtube_id == request_data.youtube_id, Video.user_id == current_user.id).first()
        if not video:
            raise HTTPException(status_code=404, detail=f"Vídeo '{request_data.youtube_id}' não encontrado ou não pertence ao usuário.")
        video_id_filter = request_data.youtube_id
    else:
        # Se não for fornecido, busca apenas nos vídeos do usuário (filtro $in no ChromaDB)
        user_video_ids = get_user_video_ids(db, current_user.id)
        if not user_video_ids:
            return []
        video_id_filter = user_video_ids
    
    try:
        resultados = execute_search_use_case(
            query=request_data.query,
            search_service=search_service,
            video_id_filter=video_id_filter,
            num_results=request_data.num_results,
            threshold=request_data.threshold
        )
        
        return resultados[:request_data.num_results]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno: {e}")