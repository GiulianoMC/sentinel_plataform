from fastapi import FastAPI, HTTPException
from app.use_cases.SemanticSearch.execute_semantic_search import execute_semantic_search


app = FastAPI(title="Plataforma Sentinela")

@app.get("/run-semantic-search")
def run_semantic_search_endpoint():
    try:
        result = execute_semantic_search()
        return {"output": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to execute script")