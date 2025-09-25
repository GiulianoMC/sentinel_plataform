from app.services.SemanticSearchService import SemanticSearchService

def execute_search_use_case(query: str, search_service: SemanticSearchService) -> list[str]:
    if not query or not isinstance(query, str):
        raise ValueError("A pergunta não pode ser vazia e deve ser uma string.")

    results = search_service.search(query=query, num_results=2)
    
    return results
