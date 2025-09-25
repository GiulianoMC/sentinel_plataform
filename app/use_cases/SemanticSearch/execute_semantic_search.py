from app.services.SemanticSearchService import SemanticSearchService

def execute_semantic_search():
    runner = SemanticSearchService()
    output = runner.run_semantic_search()
    return output