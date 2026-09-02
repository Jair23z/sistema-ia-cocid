"""Controlled sequential batch execution over the single-paper orchestrator."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from app.analysis.orchestrator import ScientificAnalysisOrchestrator
from app.analysis.retrieval_agent import InvalidPaperDataError
from app.analysis.schemas import SinglePaperAnalysisRun
from app.schemas import (
    BatchAnalysisError,
    BatchAnalysisErrorItem,
    BatchAnalysisRequest,
    BatchAnalysisResponse,
    BatchAnalysisSuccessItem,
)
from app.services.scientific_analysis import (
    AnalysisAuthenticationError,
    AnalysisConfigurationError,
    AnalysisInvalidResponseError,
    AnalysisProviderError,
    AnalysisRateLimitError,
    AnalysisTimeoutError,
)


HANDLED_BATCH_ERRORS = (
    requests.RequestException,
    InvalidPaperDataError,
    AnalysisConfigurationError,
    AnalysisAuthenticationError,
    AnalysisTimeoutError,
    AnalysisRateLimitError,
    AnalysisInvalidResponseError,
    AnalysisProviderError,
)
SYSTEMIC_BATCH_ERRORS = (
    AnalysisConfigurationError,
    AnalysisAuthenticationError,
    AnalysisRateLimitError,
)


@dataclass(frozen=True)
class BatchAnalysisRun:
    """Public batch response plus successful internal single-paper runs."""

    response: BatchAnalysisResponse
    successful_runs: tuple[SinglePaperAnalysisRun, ...]


def _safe_batch_error(error: Exception) -> BatchAnalysisError:
    if isinstance(error, requests.HTTPError):
        if error.response is not None and error.response.status_code == 404:
            return BatchAnalysisError(
                code="paper_not_found",
                message="La publicación no fue encontrada en OpenAlex.",
            )
        return BatchAnalysisError(
            code="openalex_unavailable",
            message="No fue posible consultar OpenAlex.",
        )

    if isinstance(error, requests.Timeout):
        return BatchAnalysisError(
            code="openalex_timeout",
            message="OpenAlex tardó demasiado en responder.",
        )

    if isinstance(error, requests.RequestException):
        return BatchAnalysisError(
            code="openalex_unavailable",
            message="No fue posible consultar OpenAlex.",
        )

    if isinstance(error, InvalidPaperDataError):
        return BatchAnalysisError(
            code="invalid_paper_data",
            message="OpenAlex devolvió datos de publicación no válidos.",
        )

    if isinstance(error, AnalysisConfigurationError):
        return BatchAnalysisError(
            code="analysis_not_configured",
            message="El servicio de análisis no está configurado.",
        )

    if isinstance(error, AnalysisAuthenticationError):
        return BatchAnalysisError(
            code="analysis_authentication_failed",
            message="No fue posible autenticar el servicio de análisis.",
        )

    if isinstance(error, AnalysisTimeoutError):
        return BatchAnalysisError(
            code="analysis_timeout",
            message="El servicio de análisis tardó demasiado en responder.",
        )

    if isinstance(error, AnalysisRateLimitError):
        return BatchAnalysisError(
            code="analysis_rate_limited",
            message="El servicio de análisis alcanzó temporalmente su límite.",
        )

    if isinstance(error, AnalysisInvalidResponseError):
        return BatchAnalysisError(
            code="invalid_analysis_response",
            message="El servicio de análisis devolvió una respuesta no válida.",
        )

    return BatchAnalysisError(
        code="analysis_unavailable",
        message="No fue posible completar el análisis científico.",
    )


class BatchAnalysisService:
    """Run two to five papers sequentially and isolate known item failures."""

    def __init__(self, orchestrator: ScientificAnalysisOrchestrator):
        self._orchestrator = orchestrator

    def run(self, request: BatchAnalysisRequest) -> BatchAnalysisResponse:
        return self.run_with_details(request).response

    def run_with_details(self, request: BatchAnalysisRequest) -> BatchAnalysisRun:
        results: list[BatchAnalysisSuccessItem | BatchAnalysisErrorItem] = []
        successful_runs: list[SinglePaperAnalysisRun] = []
        systemic_error: BatchAnalysisError | None = None

        for openalex_id in request.paper_ids:
            if systemic_error is not None:
                results.append(
                    BatchAnalysisErrorItem(
                        openalex_id=openalex_id,
                        status="error",
                        analysis=None,
                        error=systemic_error,
                    )
                )
                continue

            try:
                analysis_run = self._orchestrator.run(openalex_id)
            except HANDLED_BATCH_ERRORS as error:
                safe_error = _safe_batch_error(error)
                if isinstance(error, SYSTEMIC_BATCH_ERRORS):
                    systemic_error = safe_error
                results.append(
                    BatchAnalysisErrorItem(
                        openalex_id=openalex_id,
                        status="error",
                        analysis=None,
                        error=safe_error,
                    )
                )
                continue

            results.append(
                BatchAnalysisSuccessItem(
                    openalex_id=openalex_id,
                    status="success",
                    analysis=analysis_run.analysis,
                    error=None,
                )
            )
            successful_runs.append(analysis_run)

        success_count = sum(result.status == "success" for result in results)
        response = BatchAnalysisResponse(
            requested_count=len(request.paper_ids),
            processed_count=len(results),
            success_count=success_count,
            error_count=len(results) - success_count,
            results=results,
        )
        return BatchAnalysisRun(
            response=response,
            successful_runs=tuple(successful_runs),
        )
