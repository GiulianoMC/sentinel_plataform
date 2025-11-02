from app.services.SemanticSearchService import SemanticSearchService
from typing import Optional

def execute_search_use_case(
    query: str, 
    search_service: SemanticSearchService, 
    video_id_filter: Optional[str] = None
) -> list[str]:
    """
    Executa a lógica de busca semântica, agora com filtro opcional.
    """
    if not query:
        raise ValueError("A query não pode estar vazia.")
    
    # Passamos o filtro para o serviço
    resultados = search_service.search(
        query=query, 
        video_id_filter=video_id_filter
    )
    
    return resultados