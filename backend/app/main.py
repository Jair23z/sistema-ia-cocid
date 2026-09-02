from typing import Annotated, Literal

import requests
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import Paper
from app.services.openalex import get_paper_by_id, search_papers

app = FastAPI(
    title="Sistema Web de Análisis Científico y Educativo",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["GET"],
    allow_headers=[],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/papers", response_model=list[Paper])
def get_papers(
    query: Annotated[str, Query(min_length=1, max_length=300)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    from_year: Annotated[int | None, Query(ge=1000, le=2100)] = None,
    to_year: Annotated[int | None, Query(ge=1000, le=2100)] = None,
    publication_type: Annotated[
        Literal[
            "article",
            "review",
            "book",
            "book-chapter",
            "dissertation",
            "preprint",
        ]
        | None,
        Query(),
    ] = None,
    is_open_access: bool | None = None,
):
    normalized_query = query.strip()

    if not normalized_query:
        raise HTTPException(status_code=422, detail="La consulta no puede estar vacía.")

    if from_year is not None and to_year is not None and from_year > to_year:
        raise HTTPException(
            status_code=422,
            detail="El año inicial no puede ser mayor que el año final.",
        )

    try:
        return search_papers(
            normalized_query,
            limit,
            from_year,
            to_year,
            publication_type,
            is_open_access,
        )
    except requests.Timeout as error:
        raise HTTPException(
            status_code=504,
            detail="OpenAlex tardó demasiado en responder.",
        ) from error
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail="No fue posible consultar OpenAlex.",
        ) from error


@app.get("/papers/{openalex_id}", response_model=Paper)
def get_paper(
    openalex_id: Annotated[str, Path(pattern=r"^W\d+$")],
):
    try:
        return get_paper_by_id(openalex_id)
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="La publicación no fue encontrada en OpenAlex.",
            ) from error

        raise HTTPException(
            status_code=502,
            detail="No fue posible consultar OpenAlex.",
        ) from error
    except requests.Timeout as error:
        raise HTTPException(
            status_code=504,
            detail="OpenAlex tardó demasiado en responder.",
        ) from error
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail="No fue posible consultar OpenAlex.",
        ) from error
