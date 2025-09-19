from fastapi import FastAPI

app = FastAPI(title="Plataforma Sentinela")

@app.get("/")
def read_root():
    """Endpoint raiz para verificar o status da API."""
    return {"status": "API is running"}