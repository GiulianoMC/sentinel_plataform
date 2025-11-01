from app.services.SemanticSearchService import SemanticSearchService

app_state = {}

def get_search_service() -> SemanticSearchService:
    service = app_state.get('search_service')
    if not service:
        raise RuntimeError("O serviço de busca não foi inicializado.")
    return service
