from fastapi import FastAPI
from app.services.openalex import search_papers

app = FastAPI(
    title="Sistema Web de Análisis Científico y Educativo",
    version="0.1.0"
)

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/papers")
def get_papers(query: str, limit: int = 10):
    return search_papers(query, limit)