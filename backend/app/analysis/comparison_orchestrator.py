"""Orchestrate one controlled batch and one optional comparison call."""

from dataclasses import dataclass

from app.analysis.batch_service import BatchAnalysisRun, BatchAnalysisService
from app.analysis.comparison_agent import ComparisonAgent
from app.analysis.schemas import (
    ComparisonPaperEvidence,
    ComparisonUsage,
    PreparedComparisonEvidence,
)
from app.schemas import (
    BatchAnalysisRequest,
    BatchComparisonResponse,
    ComparisonPaperReference,
    ExcludedComparisonPaper,
)
from app.services.scientific_analysis import StructuredOutputRun


INSUFFICIENT_EVIDENCE_MESSAGE = (
    "La publicación fue excluida porque no tiene evidencia suficiente para "
    "una comparación científica."
)


@dataclass(frozen=True)
class BatchComparisonRun:
    response: BatchComparisonResponse
    batch_run: BatchAnalysisRun
    comparison_usage: ComparisonUsage | None


def _comparison_usage(result: StructuredOutputRun) -> ComparisonUsage:
    return ComparisonUsage(
        agent="comparison",
        model=result.model,
        input_tokens=result.input_tokens,
        cached_input_tokens=result.cached_input_tokens,
        cache_write_tokens=result.cache_write_tokens,
        output_tokens=result.output_tokens,
        total_tokens=result.total_tokens,
    )


class BatchComparisonOrchestrator:
    """Filter eligible batch runs and compare them without sending abstracts."""

    def __init__(
        self,
        batch_service: BatchAnalysisService,
        comparison_agent: ComparisonAgent,
    ):
        self._batch_service = batch_service
        self._comparison_agent = comparison_agent

    def run(self, request: BatchAnalysisRequest) -> BatchComparisonRun:
        batch_run = self._batch_service.run_with_details(request)
        successful_runs = {
            run.openalex_id: run for run in batch_run.successful_runs
        }
        comparable_evidence: list[ComparisonPaperEvidence] = []
        considered_papers: list[ComparisonPaperReference] = []
        excluded_papers: list[ExcludedComparisonPaper] = []

        for result in batch_run.response.results:
            if result.status == "error":
                excluded_papers.append(
                    ExcludedComparisonPaper(
                        openalex_id=result.openalex_id,
                        reason="analysis_error",
                        message=result.error.message,
                        error_code=result.error.code,
                    )
                )
                continue

            analysis_run = successful_runs.get(result.openalex_id)
            if analysis_run is None:
                raise RuntimeError("A successful batch result has no internal run.")

            evidence = analysis_run.prepared_evidence.evidence
            if not analysis_run.prepared_evidence.is_sufficient:
                excluded_papers.append(
                    ExcludedComparisonPaper(
                        openalex_id=result.openalex_id,
                        reason="insufficient_evidence",
                        message=INSUFFICIENT_EVIDENCE_MESSAGE,
                        error_code=None,
                    )
                )
                continue

            comparable_evidence.append(
                ComparisonPaperEvidence(
                    openalex_id=result.openalex_id,
                    title=evidence.title,
                    doi=evidence.doi,
                    year=evidence.year,
                    source=evidence.source,
                    analysis=analysis_run.analysis,
                )
            )
            considered_papers.append(
                ComparisonPaperReference(
                    openalex_id=result.openalex_id,
                    title=evidence.title,
                    doi=evidence.doi,
                    year=evidence.year,
                    source=evidence.source,
                )
            )

        if len(comparable_evidence) < 2:
            response = BatchComparisonResponse(
                batch_analysis=batch_run.response,
                comparison_status="insufficient_comparable_papers",
                considered_count=len(considered_papers),
                considered_papers=considered_papers,
                excluded_papers=excluded_papers,
                comparison=None,
            )
            return BatchComparisonRun(
                response=response,
                batch_run=batch_run,
                comparison_usage=None,
            )

        prepared_evidence = PreparedComparisonEvidence(
            papers=comparable_evidence,
        )
        comparison_result = self._comparison_agent.run(prepared_evidence)
        response = BatchComparisonResponse(
            batch_analysis=batch_run.response,
            comparison_status="completed",
            considered_count=len(considered_papers),
            considered_papers=considered_papers,
            excluded_papers=excluded_papers,
            comparison=comparison_result.output,
        )
        return BatchComparisonRun(
            response=response,
            batch_run=batch_run,
            comparison_usage=_comparison_usage(comparison_result),
        )
