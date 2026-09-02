from typing import Annotated, Literal

import requests
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware

from app.analysis import ScientificAnalysisOrchestrator
from app.analysis.batch_service import BatchAnalysisService
from app.analysis.comparison_agent import ComparisonAgent
from app.analysis.comparison_orchestrator import BatchComparisonOrchestrator
from app.analysis.retrieval_agent import (
    InvalidOpenAlexIdError,
    InvalidPaperDataError,
)
from app.schemas import (
    BatchAnalysisRequest,
    BatchAnalysisResponse,
    BatchComparisonResponse,
    Paper,
    ScientificAnalysis,
)
from app.services.openalex import get_paper_by_id, search_papers
from app.services.scientific_analysis import (
    AnalysisAuthenticationError,
    AnalysisConfigurationError,
    AnalysisInvalidResponseError,
    AnalysisProviderError,
    AnalysisRateLimitError,
    AnalysisTimeoutError,
    ScientificAnalysisLLMService,
)

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
    allow_methods=["GET", "POST"],
    allow_headers=[],
)

scientific_analysis_llm_service = ScientificAnalysisLLMService()
scientific_analysis_orchestrator = ScientificAnalysisOrchestrator(
    llm_service=scientific_analysis_llm_service,
)
batch_analysis_service = BatchAnalysisService(scientific_analysis_orchestrator)
comparison_agent = ComparisonAgent(scientific_analysis_llm_service)
batch_comparison_orchestrator = BatchComparisonOrchestrator(
    batch_analysis_service,
    comparison_agent,
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


@app.post("/papers/batch-analysis", response_model=BatchAnalysisResponse)
def create_batch_analysis(request: BatchAnalysisRequest):
    return batch_analysis_service.run(request)


@app.post("/papers/batch-comparison", response_model=BatchComparisonResponse)
def create_batch_comparison(request: BatchAnalysisRequest):
    try:
        return batch_comparison_orchestrator.run(request).response
    except AnalysisConfigurationError as error:
        raise HTTPException(
            status_code=503,
            detail="El servicio de comparación no está configurado.",
        ) from error
    except AnalysisAuthenticationError as error:
        raise HTTPException(
            status_code=503,
            detail="No fue posible autenticar el servicio de comparación.",
        ) from error
    except AnalysisTimeoutError as error:
        raise HTTPException(
            status_code=504,
            detail="El servicio de comparación tardó demasiado en responder.",
        ) from error
    except AnalysisRateLimitError as error:
        raise HTTPException(
            status_code=503,
            detail="El servicio de comparación alcanzó temporalmente su límite.",
        ) from error
    except AnalysisInvalidResponseError as error:
        raise HTTPException(
            status_code=502,
            detail="El servicio de comparación devolvió una respuesta no válida.",
        ) from error
    except AnalysisProviderError as error:
        raise HTTPException(
            status_code=502,
            detail="No fue posible completar la comparación científica.",
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


@app.post("/papers/{openalex_id}/analysis", response_model=ScientificAnalysis)
def create_paper_analysis(
    openalex_id: Annotated[str, Path(pattern=r"^W\d+$")],
):
    try:
        return scientific_analysis_orchestrator.run(openalex_id).analysis
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
    except InvalidPaperDataError as error:
        raise HTTPException(
            status_code=502,
            detail="OpenAlex devolvió datos de publicación no válidos.",
        ) from error
    except InvalidOpenAlexIdError as error:
        raise HTTPException(
            status_code=422,
            detail="El identificador de OpenAlex no es válido.",
        ) from error
    except AnalysisConfigurationError as error:
        raise HTTPException(
            status_code=503,
            detail="El servicio de análisis no está configurado.",
        ) from error
    except AnalysisAuthenticationError as error:
        raise HTTPException(
            status_code=503,
            detail="No fue posible autenticar el servicio de análisis.",
        ) from error
    except AnalysisTimeoutError as error:
        raise HTTPException(
            status_code=504,
            detail="El servicio de análisis tardó demasiado en responder.",
        ) from error
    except AnalysisRateLimitError as error:
        raise HTTPException(
            status_code=503,
            detail="El servicio de análisis alcanzó temporalmente su límite.",
        ) from error
    except AnalysisInvalidResponseError as error:
        raise HTTPException(
            status_code=502,
            detail="El servicio de análisis devolvió una respuesta no válida.",
        ) from error
    except AnalysisProviderError as error:
        raise HTTPException(
            status_code=502,
            detail="No fue posible completar el análisis científico.",
        ) from error
