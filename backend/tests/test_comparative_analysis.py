import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.analysis.batch_service import BatchAnalysisRun, BatchAnalysisService
from app.analysis.comparison_agent import ComparisonAgent
from app.analysis.comparison_orchestrator import BatchComparisonOrchestrator
from app.analysis.schemas import (
    ComparisonPaperEvidence,
    PreparedComparisonEvidence,
    PreparedScientificEvidence,
    ScientificEvidence,
    build_insufficient_analysis,
)
from app.main import app
from app.schemas import (
    BatchAnalysisError,
    BatchAnalysisErrorItem,
    BatchAnalysisRequest,
    BatchAnalysisResponse,
    BatchAnalysisSuccessItem,
    ComparativePoint,
    ComparativeScientificAnalysis,
    ScientificAnalysis,
)
from app.services.scientific_analysis import (
    AnalysisInvalidResponseError,
    AnalysisProviderError,
    ScientificAnalysisLLMService,
    StructuredOutputRun,
    get_openai_configuration,
)


SUFFICIENT_ABSTRACT = " ".join(f"palabra{index}" for index in range(45))


def scientific_analysis(label: str) -> ScientificAnalysis:
    return ScientificAnalysis(
        objective=f"Objetivo verificado de {label}.",
        methodology=f"Metodología verificada de {label}.",
        results=f"Resultados verificados de {label}.",
        conclusions=f"Conclusiones verificadas de {label}.",
        findings=[f"Hallazgo verificado de {label}."],
    )


def comparison(ids: list[str]) -> ComparativeScientificAnalysis:
    shared_ids = ids[:2]
    return ComparativeScientificAnalysis(
        summary="La comparación se limita al conjunto de publicaciones recibido.",
        common_points=[
            ComparativePoint(
                text="Los estudios comparten un objetivo relacionado.",
                supporting_papers=shared_ids,
            )
        ],
        differences=[
            ComparativePoint(
                text="Los estudios describen metodologías diferentes.",
                supporting_papers=shared_ids,
            )
        ],
        trends=[
            ComparativePoint(
                text="En la muestra se observa atención al mismo problema.",
                supporting_papers=shared_ids,
            )
        ],
        research_gaps=[
            ComparativePoint(
                text=(
                    "Entre las publicaciones analizadas se identificó poca "
                    "evidencia longitudinal."
                ),
                supporting_papers=[ids[0]],
            )
        ],
    )


def structured_comparison(ids: list[str]) -> StructuredOutputRun:
    return StructuredOutputRun(
        output=comparison(ids),
        model="comparison-model",
        input_tokens=300,
        cached_input_tokens=30,
        cache_write_tokens=0,
        output_tokens=120,
        total_tokens=420,
    )


def single_run(openalex_id: str, *, sufficient: bool = True) -> SimpleNamespace:
    evidence = ScientificEvidence(
        title=f"Título {openalex_id}",
        abstract=SUFFICIENT_ABSTRACT if sufficient else None,
        authors=["Autora de prueba"],
        source="Revista de prueba",
        year=2024,
        publication_date="2024-01-01",
        publication_type="article",
        doi=f"https://doi.org/10.1000/{openalex_id}",
    )
    prepared = PreparedScientificEvidence(
        openalex_id=openalex_id,
        evidence=evidence,
        abstract_word_count=45 if sufficient else 0,
        is_sufficient=sufficient,
        insufficiency_reason=None if sufficient else "missing_abstract",
    )
    return SimpleNamespace(
        openalex_id=openalex_id,
        prepared_evidence=prepared,
        analysis=(
            scientific_analysis(openalex_id)
            if sufficient
            else build_insufficient_analysis()
        ),
        agent_usages=[],
    )


def batch_run(
    runs: list[SimpleNamespace],
    error_ids: list[str] | None = None,
) -> BatchAnalysisRun:
    error_ids = error_ids or []
    results = [
        BatchAnalysisSuccessItem(
            openalex_id=run.openalex_id,
            status="success",
            analysis=run.analysis,
            error=None,
        )
        for run in runs
    ]
    results.extend(
        BatchAnalysisErrorItem(
            openalex_id=openalex_id,
            status="error",
            analysis=None,
            error=BatchAnalysisError(
                code="paper_not_found",
                message="La publicación no fue encontrada en OpenAlex.",
            ),
        )
        for openalex_id in error_ids
    )
    success_count = len(runs)
    response = BatchAnalysisResponse(
        requested_count=len(results),
        processed_count=len(results),
        success_count=success_count,
        error_count=len(error_ids),
        results=results,
    )
    return BatchAnalysisRun(response=response, successful_runs=tuple(runs))


def prepared_comparison(ids: list[str]) -> PreparedComparisonEvidence:
    return PreparedComparisonEvidence(
        papers=[
            ComparisonPaperEvidence(
                openalex_id=openalex_id,
                title=f"Título {openalex_id}",
                doi=f"https://doi.org/10.1000/{openalex_id}",
                year=2024,
                source="Revista de prueba",
                analysis=scientific_analysis(openalex_id),
            )
            for openalex_id in ids
        ]
    )


class ComparativeSchemaTests(unittest.TestCase):
    def test_rejects_duplicate_references(self):
        with self.assertRaises(ValidationError):
            ComparativePoint(
                text="Punto duplicado.",
                supporting_papers=["W1", "W1"],
            )

    def test_requires_two_references_except_for_research_gaps(self):
        with self.assertRaises(ValidationError):
            ComparativeScientificAnalysis(
                summary="Resumen limitado a la muestra.",
                common_points=[
                    ComparativePoint(
                        text="Coincidencia aislada.",
                        supporting_papers=["W1"],
                    )
                ],
                differences=[],
                trends=[],
                research_gaps=[],
            )

        valid = comparison(["W1", "W2"])
        self.assertEqual(valid.research_gaps[0].supporting_papers, ["W1"])

    def test_rejects_unscoped_or_universal_research_gaps(self):
        invalid_gaps = [
            "Falta evidencia longitudinal.",
            "Entre las publicaciones analizadas no existen investigaciones útiles.",
            "En el conjunto seleccionado nunca se ha estudiado este método.",
            "Esta muestra presenta poca evidencia sobre un tema que jamás se ha investigado.",
            "Entre las publicaciones analizadas ningún estudio aborda esta variable.",
        ]

        for gap in invalid_gaps:
            with self.subTest(gap=gap):
                with self.assertRaises(ValidationError):
                    ComparativeScientificAnalysis(
                        summary="Resumen limitado a la muestra.",
                        common_points=[],
                        differences=[],
                        trends=[],
                        research_gaps=[
                            ComparativePoint(
                                text=gap,
                                supporting_papers=["W1"],
                            )
                        ],
                    )


class ComparisonAgentTests(unittest.TestCase):
    def test_sends_only_verified_analyses_and_traceability_metadata(self):
        llm_service = Mock(spec=ScientificAnalysisLLMService)
        llm_service.run_structured.return_value = structured_comparison(
            ["W1", "W2"]
        )
        agent = ComparisonAgent(llm_service)

        result = agent.run(prepared_comparison(["W1", "W2"]))

        self.assertEqual(result.output.summary, comparison(["W1", "W2"]).summary)
        llm_service.run_structured.assert_called_once()
        call_kwargs = llm_service.run_structured.call_args.kwargs
        self.assertEqual(call_kwargs["role"], "comparison")
        self.assertIs(call_kwargs["output_schema"], ComparativeScientificAnalysis)
        self.assertEqual(
            set(call_kwargs["payload"]["papers"][0]),
            {"openalex_id", "title", "doi", "year", "source", "analysis"},
        )
        self.assertNotIn("abstract", str(call_kwargs["payload"]).casefold())

    def test_rejects_unknown_or_excluded_references(self):
        llm_service = Mock(spec=ScientificAnalysisLLMService)
        invalid_output = comparison(["W1", "W999"])
        llm_service.run_structured.return_value = StructuredOutputRun(
            output=invalid_output,
            model="comparison-model",
            input_tokens=1,
            cached_input_tokens=0,
            cache_write_tokens=0,
            output_tokens=1,
            total_tokens=2,
        )

        with self.assertRaises(AnalysisInvalidResponseError):
            ComparisonAgent(llm_service).run(
                prepared_comparison(["W1", "W2"])
            )

    def test_propagates_structured_output_and_provider_errors(self):
        for error in (
            AnalysisInvalidResponseError("private invalid output"),
            AnalysisProviderError("private provider detail"),
        ):
            with self.subTest(error=type(error).__name__):
                llm_service = Mock(spec=ScientificAnalysisLLMService)
                llm_service.run_structured.side_effect = error
                with self.assertRaises(type(error)):
                    ComparisonAgent(llm_service).run(
                        prepared_comparison(["W1", "W2"])
                    )


class BatchComparisonOrchestratorTests(unittest.TestCase):
    def build_orchestrator(self, prepared_batch: BatchAnalysisRun):
        batch_service = Mock(spec=BatchAnalysisService)
        batch_service.run_with_details.return_value = prepared_batch
        comparison_agent = Mock(spec=ComparisonAgent)
        comparison_agent.run.side_effect = lambda evidence: structured_comparison(
            [paper.openalex_id for paper in evidence.papers]
        )
        return (
            BatchComparisonOrchestrator(batch_service, comparison_agent),
            batch_service,
            comparison_agent,
        )

    def test_two_and_five_eligible_papers_make_one_comparison_call(self):
        for count in (2, 5):
            ids = [f"W{index}" for index in range(1, count + 1)]
            prepared_batch = batch_run([single_run(item) for item in ids])
            orchestrator, batch_service, comparison_agent = (
                self.build_orchestrator(prepared_batch)
            )
            request = BatchAnalysisRequest(paper_ids=ids)

            result = orchestrator.run(request)

            batch_service.run_with_details.assert_called_once_with(request)
            comparison_agent.run.assert_called_once()
            self.assertEqual(result.response.comparison_status, "completed")
            self.assertEqual(result.response.considered_count, count)
            self.assertEqual(result.comparison_usage.total_tokens, 420)

    def test_failed_and_insufficient_papers_are_excluded_before_comparison(self):
        runs = [
            single_run("W1"),
            single_run("W2"),
            single_run("W3", sufficient=False),
        ]
        orchestrator, _, comparison_agent = self.build_orchestrator(
            batch_run(runs, error_ids=["W4"])
        )

        result = orchestrator.run(
            BatchAnalysisRequest(paper_ids=["W1", "W2", "W3", "W4"])
        )

        sent_evidence = comparison_agent.run.call_args.args[0]
        self.assertEqual(
            [paper.openalex_id for paper in sent_evidence.papers],
            ["W1", "W2"],
        )
        self.assertEqual(
            [paper.openalex_id for paper in result.response.excluded_papers],
            ["W3", "W4"],
        )
        self.assertEqual(
            [paper.reason for paper in result.response.excluded_papers],
            ["insufficient_evidence", "analysis_error"],
        )

    def test_fewer_than_two_eligible_papers_make_zero_comparison_calls(self):
        runs = [single_run("W1"), single_run("W2", sufficient=False)]
        orchestrator, _, comparison_agent = self.build_orchestrator(
            batch_run(runs, error_ids=["W3"])
        )

        result = orchestrator.run(
            BatchAnalysisRequest(paper_ids=["W1", "W2", "W3"])
        )

        comparison_agent.run.assert_not_called()
        self.assertEqual(
            result.response.comparison_status,
            "insufficient_comparable_papers",
        )
        self.assertIsNone(result.response.comparison)
        self.assertIsNone(result.comparison_usage)
        self.assertEqual(result.response.considered_count, 1)


class ComparisonModelConfigurationTests(unittest.TestCase):
    def test_comparison_model_falls_back_and_supports_override(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "base-model",
                "OPENAI_COMPARISON_MODEL": "",
            },
            clear=True,
        ):
            fallback = get_openai_configuration("comparison")

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "base-model",
                "OPENAI_COMPARISON_MODEL": "comparison-override",
            },
            clear=True,
        ):
            override = get_openai_configuration("comparison")

        self.assertEqual(fallback.model, "base-model")
        self.assertEqual(override.model, "comparison-override")

    @patch("app.services.scientific_analysis.OpenAI")
    def test_comparison_uses_shared_responses_adapter_without_tools(
        self,
        mock_openai,
    ):
        output = comparison(["W1", "W2"])
        usage = SimpleNamespace(
            input_tokens=300,
            output_tokens=120,
            total_tokens=420,
            input_tokens_details=SimpleNamespace(
                cached_tokens=30,
                cache_write_tokens=0,
            ),
        )
        client = mock_openai.return_value
        client.responses.parse.return_value = SimpleNamespace(
            output_parsed=output,
            usage=usage,
        )
        service = ScientificAnalysisLLMService()

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "base-model",
                "OPENAI_COMPARISON_MODEL": "comparison-model",
            },
            clear=True,
        ):
            result = service.run_structured(
                role="comparison",
                instructions="comparison instructions",
                payload={"papers": []},
                data_label="COMPARISON_DATA",
                output_schema=ComparativeScientificAnalysis,
                max_output_tokens=3500,
            )

        mock_openai.assert_called_once_with(
            api_key="test-key",
            timeout=30.0,
            max_retries=0,
        )
        client.responses.parse.assert_called_once()
        call_kwargs = client.responses.parse.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "comparison-model")
        self.assertEqual(call_kwargs["tools"], [])
        self.assertFalse(call_kwargs["store"])
        self.assertIs(call_kwargs["text_format"], ComparativeScientificAnalysis)
        self.assertEqual(result.total_tokens, 420)


class BatchComparisonEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def completed_run(self):
        prepared_batch = batch_run([single_run("W1"), single_run("W2")])
        comparison_agent = Mock(spec=ComparisonAgent)
        comparison_agent.run.return_value = structured_comparison(["W1", "W2"])
        batch_service = Mock(spec=BatchAnalysisService)
        batch_service.run_with_details.return_value = prepared_batch
        return BatchComparisonOrchestrator(
            batch_service,
            comparison_agent,
        ).run(BatchAnalysisRequest(paper_ids=["W1", "W2"]))

    def test_endpoint_returns_the_exact_comparison_contract(self):
        comparison_orchestrator = Mock(spec=BatchComparisonOrchestrator)
        comparison_orchestrator.run.return_value = self.completed_run()

        with patch(
            "app.main.batch_comparison_orchestrator",
            comparison_orchestrator,
        ):
            response = self.client.post(
                "/papers/batch-comparison",
                json={"paper_ids": ["W1", "W2"]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()),
            {
                "batch_analysis",
                "comparison_status",
                "considered_count",
                "considered_papers",
                "excluded_papers",
                "comparison",
            },
        )
        comparison_orchestrator.run.assert_called_once()

    def test_provider_details_are_not_exposed(self):
        comparison_orchestrator = Mock(spec=BatchComparisonOrchestrator)
        comparison_orchestrator.run.side_effect = AnalysisProviderError(
            "private provider detail"
        )

        with patch(
            "app.main.batch_comparison_orchestrator",
            comparison_orchestrator,
        ):
            response = self.client.post(
                "/papers/batch-comparison",
                json={"paper_ids": ["W1", "W2"]},
            )

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private", response.text)
        self.assertEqual(
            response.json()["detail"],
            "No fue posible completar la comparación científica.",
        )


if __name__ == "__main__":
    unittest.main()
