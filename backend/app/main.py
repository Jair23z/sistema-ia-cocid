from typing import Annotated, Literal
from uuid import UUID

import requests
from fastapi import FastAPI, File, HTTPException, Path, Query, UploadFile
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
    ChunkedDocument,
    DocumentAnswerResponse,
    DocumentQuestionRequest,
    DocumentUploadResponse,
    ExtractedDocument,
    Paper,
    ScientificAnalysis,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from app.services.document_storage import (
    DocumentNotFoundError,
    DocumentStorageError,
    DocumentStorageService,
    DocumentTooLargeError,
    EmptyDocumentError,
    InvalidPdfSignatureError,
    UnsupportedDocumentError,
)
from app.services.document_chunking import DocumentChunkingService
from app.services.document_rag import (
    DocumentRagService,
    RagAuthenticationError,
    RagConfigurationError,
    RagInvalidResponseError,
    RagProviderError,
    RagRateLimitError,
    RagTimeoutError,
)
from app.services.embeddings import (
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingDataIntegrityError,
    EmbeddingInvalidResponseError,
    EmbeddingProviderError,
    EmbeddingRateLimitError,
    EmbeddingService,
    EmbeddingTimeoutError,
)
from app.services.pdf_extraction import (
    MAX_PDF_PAGES,
    PdfEncryptedError,
    PdfExtractionError,
    PdfExtractionService,
    PdfPageLimitExceededError,
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
from app.services.semantic_retrieval import (
    InsufficientDocumentTextError,
    SemanticRetrievalService,
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
document_storage_service = DocumentStorageService()
pdf_extraction_service = PdfExtractionService(document_storage_service)
document_chunking_service = DocumentChunkingService(pdf_extraction_service)
embedding_service = EmbeddingService()
semantic_retrieval_service = SemanticRetrievalService(
    document_chunking_service,
    embedding_service,
)
document_rag_service = DocumentRagService(semantic_retrieval_service)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    status_code=201,
)
async def upload_document(
    file: Annotated[UploadFile, File(description="PDF científico")],
):
    try:
        stored_document = await document_storage_service.save_pdf(file)
    except EmptyDocumentError as error:
        raise HTTPException(
            status_code=400,
            detail="El archivo PDF está vacío.",
        ) from error
    except (UnsupportedDocumentError, InvalidPdfSignatureError) as error:
        raise HTTPException(
            status_code=415,
            detail="El archivo debe ser un PDF válido con MIME application/pdf.",
        ) from error
    except DocumentTooLargeError as error:
        raise HTTPException(
            status_code=413,
            detail="El archivo PDF supera el límite permitido de 15 MiB.",
        ) from error
    except DocumentStorageError as error:
        raise HTTPException(
            status_code=500,
            detail="No fue posible almacenar el documento.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="No fue posible almacenar el documento.",
        ) from error
    finally:
        try:
            await file.close()
        except Exception:
            pass

    return DocumentUploadResponse(
        document_id=stored_document.document_id,
        filename=stored_document.public_filename,
        size_bytes=stored_document.size_bytes,
        status="uploaded",
    )


@app.post(
    "/documents/{document_id}/extract",
    response_model=ExtractedDocument,
)
def extract_document(document_id: UUID):
    try:
        return pdf_extraction_service.extract(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="El documento no fue encontrado.",
        ) from error
    except PdfPageLimitExceededError as error:
        raise HTTPException(
            status_code=422,
            detail=(
                "El documento supera el límite permitido de "
                f"{MAX_PDF_PAGES} páginas."
            ),
        ) from error
    except PdfEncryptedError as error:
        raise HTTPException(
            status_code=422,
            detail="No es posible procesar un PDF cifrado o protegido con contraseña.",
        ) from error
    except PdfExtractionError as error:
        raise HTTPException(
            status_code=422,
            detail="El archivo PDF está corrupto o no tiene una estructura procesable.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="No fue posible extraer el contenido del documento.",
        ) from error


@app.post(
    "/documents/{document_id}/chunks",
    response_model=ChunkedDocument,
)
def chunk_document(document_id: UUID):
    try:
        return document_chunking_service.chunk_document(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="El documento no fue encontrado.",
        ) from error
    except PdfPageLimitExceededError as error:
        raise HTTPException(
            status_code=422,
            detail=(
                "El documento supera el límite permitido de "
                f"{MAX_PDF_PAGES} páginas."
            ),
        ) from error
    except PdfEncryptedError as error:
        raise HTTPException(
            status_code=422,
            detail="No es posible procesar un PDF cifrado o protegido con contraseña.",
        ) from error
    except PdfExtractionError as error:
        raise HTTPException(
            status_code=422,
            detail="El archivo PDF está corrupto o no tiene una estructura procesable.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="No fue posible preparar el contenido del documento.",
        ) from error


@app.post(
    "/documents/{document_id}/search",
    response_model=SemanticSearchResponse,
)
def search_document(
    document_id: UUID,
    request: SemanticSearchRequest,
):
    try:
        return semantic_retrieval_service.search_document(
            document_id,
            request,
        ).response
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="El documento no fue encontrado.",
        ) from error
    except PdfPageLimitExceededError as error:
        raise HTTPException(
            status_code=422,
            detail=(
                "El documento supera el límite permitido de "
                f"{MAX_PDF_PAGES} páginas."
            ),
        ) from error
    except PdfEncryptedError as error:
        raise HTTPException(
            status_code=422,
            detail="No es posible procesar un PDF cifrado o protegido con contraseña.",
        ) from error
    except PdfExtractionError as error:
        raise HTTPException(
            status_code=422,
            detail="El archivo PDF está corrupto o no tiene una estructura procesable.",
        ) from error
    except InsufficientDocumentTextError as error:
        raise HTTPException(
            status_code=422,
            detail=(
                "El documento no contiene suficiente texto extraíble para "
                "realizar una búsqueda semántica."
            ),
        ) from error
    except EmbeddingConfigurationError as error:
        raise HTTPException(
            status_code=503,
            detail="El servicio de búsqueda semántica no está configurado.",
        ) from error
    except EmbeddingAuthenticationError as error:
        raise HTTPException(
            status_code=503,
            detail="No fue posible autenticar el servicio de búsqueda semántica.",
        ) from error
    except EmbeddingTimeoutError as error:
        raise HTTPException(
            status_code=504,
            detail="La búsqueda semántica tardó demasiado en responder.",
        ) from error
    except EmbeddingRateLimitError as error:
        raise HTTPException(
            status_code=503,
            detail="El servicio de búsqueda semántica alcanzó temporalmente su límite.",
        ) from error
    except (EmbeddingInvalidResponseError, EmbeddingDataIntegrityError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail="El servicio de búsqueda semántica devolvió una respuesta no válida.",
        ) from error
    except EmbeddingProviderError as error:
        raise HTTPException(
            status_code=502,
            detail="No fue posible completar la búsqueda semántica.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="No fue posible buscar dentro del documento.",
        ) from error


@app.post(
    "/documents/{document_id}/ask",
    response_model=DocumentAnswerResponse,
)
def ask_document(
    document_id: UUID,
    request: DocumentQuestionRequest,
):
    try:
        return document_rag_service.ask_document(document_id, request).response
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="El documento no fue encontrado.",
        ) from error
    except PdfPageLimitExceededError as error:
        raise HTTPException(
            status_code=422,
            detail=(
                "El documento supera el límite permitido de "
                f"{MAX_PDF_PAGES} páginas."
            ),
        ) from error
    except PdfEncryptedError as error:
        raise HTTPException(
            status_code=422,
            detail="No es posible procesar un PDF cifrado o protegido con contraseña.",
        ) from error
    except PdfExtractionError as error:
        raise HTTPException(
            status_code=422,
            detail="El archivo PDF está corrupto o no tiene una estructura procesable.",
        ) from error
    except InsufficientDocumentTextError as error:
        raise HTTPException(
            status_code=422,
            detail=(
                "El documento no contiene suficiente texto extraíble para "
                "responder preguntas."
            ),
        ) from error
    except EmbeddingConfigurationError as error:
        raise HTTPException(
            status_code=503,
            detail="El servicio de búsqueda semántica no está configurado.",
        ) from error
    except EmbeddingAuthenticationError as error:
        raise HTTPException(
            status_code=503,
            detail="No fue posible autenticar el servicio de búsqueda semántica.",
        ) from error
    except EmbeddingTimeoutError as error:
        raise HTTPException(
            status_code=504,
            detail="La búsqueda semántica tardó demasiado en responder.",
        ) from error
    except EmbeddingRateLimitError as error:
        raise HTTPException(
            status_code=503,
            detail="El servicio de búsqueda semántica alcanzó temporalmente su límite.",
        ) from error
    except (EmbeddingInvalidResponseError, EmbeddingDataIntegrityError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail="El servicio de búsqueda semántica devolvió una respuesta no válida.",
        ) from error
    except EmbeddingProviderError as error:
        raise HTTPException(
            status_code=502,
            detail="No fue posible completar la búsqueda semántica.",
        ) from error
    except RagConfigurationError as error:
        raise HTTPException(
            status_code=503,
            detail="El servicio de consulta documental no está configurado.",
        ) from error
    except RagAuthenticationError as error:
        raise HTTPException(
            status_code=503,
            detail="No fue posible autenticar el servicio de consulta documental.",
        ) from error
    except RagTimeoutError as error:
        raise HTTPException(
            status_code=504,
            detail="La consulta documental tardó demasiado en responder.",
        ) from error
    except RagRateLimitError as error:
        raise HTTPException(
            status_code=503,
            detail="El servicio de consulta documental alcanzó temporalmente su límite.",
        ) from error
    except RagInvalidResponseError as error:
        raise HTTPException(
            status_code=502,
            detail="El servicio de consulta documental devolvió una respuesta no válida.",
        ) from error
    except RagProviderError as error:
        raise HTTPException(
            status_code=502,
            detail="No fue posible completar la consulta documental.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="No fue posible responder la pregunta sobre el documento.",
        ) from error


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
