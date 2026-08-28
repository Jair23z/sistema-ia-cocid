import requests

BASE_URL = "https://api.openalex.org/works"

def search_papers(query: str, limit: int = 10):
    params = {
        "search": query,
        "per-page": limit
    }

    response = requests.get(BASE_URL, params=params, timeout=20)
    response.raise_for_status()

    data = response.json()

    papers = []

    for work in data.get("results", []):
        papers.append({
            "id": work.get("id"),
            "title": work.get("display_name"),
            "year": work.get("publication_year"),
            "doi": work.get("doi"),
            "citations": work.get("cited_by_count"),
        })

    return papers