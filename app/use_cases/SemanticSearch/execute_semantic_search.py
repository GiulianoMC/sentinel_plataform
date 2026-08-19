from app.services.SemanticSearchService import SemanticSearchService
from typing import Optional, List, Dict, Any, Union

def execute_search_use_case(
    query: str, 
    search_service: SemanticSearchService, 
    video_id_filter: Optional[Union[str, List[str]]] = None,
    num_results: int = 10,
    threshold: float = 0.6
) -> List[Dict[str, Any]]:
    """
    Executa a lógica de busca semântica, agora com filtro opcional e threshold.
    """
    if not query:
        raise ValueError("A query não pode estar vazia.")
    
    resultados = search_service.search(
        query=query, 
        video_id_filter=video_id_filter,
        num_results=num_results,
        threshold=threshold
    )
    
    return resultados