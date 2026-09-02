import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import requests
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.analysis.batch_service import BatchAnalysisService
from app.analysis.orchestrator import ScientificAnalysisOrchestrator
from app.analysis.schemas import build_insufficient_analysis
from app.main import app
from app.schemas import BatchAnalysisRequest, ScientificAnalysis
from app.services.scientific_analysis import (
    AnalysisConfigurationError,
    AnalysisProviderError,
)


def valid_analysis(label: str = "paper") -> ScientificAnalysis:
    return ScientificAnalysis(
        objective=f"Objetivo de {label}.",
        methodology=f"Metodología de {label}.",
        results=f"Resultados de {label}.",
        conclusions=f"Conclusiones de {label}.",
        findings=[f"Hallazgo de {label}."],
    )


def successful_run(label: str = "paper") -> SimpleNamespace:
    return SimpleNamespace(analysis=valid_analysis(label))


class BatchAnalysisRequestTests(unittest.TestCase):
    def test_accepts_the_minimum_and_maximum_unique_limits(self):
        minimum = BatchAnalysisRequest(paper_ids=["W1", "W2"])
        maximum = BatchAnalysisRequest(
            paper_ids=["W1", "W2", "W3", "W4", "W5"]
        )

        self.assertEqual(len(minimum.paper_ids), 2)
        self.assertEqual(len(maximum.paper_ids), 5)

    def test_requires_between_two_and_five_ids(self):
        invalid_lists = [
            ["W1"],
            ["W1", "W2", "W3", "W4", "W5", "W6"],
        ]

        for paper_ids in invalid_lists:
            with self.subTest(paper_ids=paper_ids):
                with self.assertRaises(ValidationError):
                    BatchAnalysisRequest(paper_ids=paper_ids)

    def test_rejects_invalid_ids(self):
        for invalid_id in (
            "123",
            "w123",
            "Wabc",
            "W123/analysis",
            " W123 ",
        ):
            with self.subTest(invalid_id=invalid_id):
                with self.assertRaises(ValidationError):
                    BatchAnalysisRequest(paper_ids=["W1", invalid_id])

    def test_deduplicates_in_first_occurrence_order(self):
        request = BatchAnalysisRequest(
            paper_ids=["W2", "W1", "W2", "W3", "W1"]
        )

        self.assertEqual(request.paper_ids, ["W2", "W1", "W3"])

    def test_duplicates_must_leave_at_least_two_unique_ids(self):
        with self.assertRaises(ValidationError):
            BatchAnalysisRequest(paper_ids=["W1", "W1"])


class BatchAnalysisServiceTests(unittest.TestCase):
    def test_internal_run_reuses_the_same_public_batch_execution(self):
        first_run = successful_run("W1")
        second_run = successful_run("W2")
        orchestrator = Mock(spec=ScientificAnalysisOrchestrator)
        orchestrator.run.side_effect = [first_run, second_run]
        service = BatchAnalysisService(orchestrator)

        internal_run = service.run_with_details(
            BatchAnalysisRequest(paper_ids=["W1", "W2"])
        )

        self.assertEqual(orchestrator.run.call_count, 2)
        self.assertEqual(internal_run.response.success_count, 2)
        self.assertEqual(internal_run.successful_runs, (first_run, second_run))

    def test_runs_each_unique_paper_once_and_keeps_order(self):
        orchestrator = Mock(spec=ScientificAnalysisOrchestrator)
        orchestrator.run.side_effect = [
            successful_run("W2"),
            successful_run("W1"),
            successful_run("W3"),
        ]
        service = BatchAnalysisService(orchestrator)
        request = BatchAnalysisRequest(
            paper_ids=["W2", "W1", "W2", "W3"]
        )

        response = service.run(request)

        self.assertEqual(
            orchestrator.run.call_args_list,
            [call("W2"), call("W1"), call("W3")],
        )
        self.assertEqual(
            [result.openalex_id for result in response.results],
            ["W2", "W1", "W3"],
        )
        self.assertEqual(response.requested_count, 3)
        self.assertEqual(response.processed_count, 3)
        self.assertEqual(response.success_count, 3)
        self.assertEqual(response.error_count, 0)

    def test_isolates_one_failure_and_continues_with_remaining_papers(self):
        orchestrator = Mock(spec=ScientificAnalysisOrchestrator)
        orchestrator.run.side_effect = [
            successful_run("W1"),
            AnalysisProviderError("private provider detail"),
            successful_run("W3"),
        ]
        response = BatchAnalysisService(orchestrator).run(
            BatchAnalysisRequest(paper_ids=["W1", "W2", "W3"])
        )

        self.assertEqual(orchestrator.run.call_count, 3)
        self.assertEqual(response.success_count, 2)
        self.assertEqual(response.error_count, 1)
        failed = response.results[1]
        self.assertEqual(failed.status, "error")
        self.assertEqual(failed.error.code, "analysis_unavailable")
        self.assertNotIn("private", failed.error.message)

        serialized = response.model_dump(mode="json")
        self.assertNotIn("prepared_evidence", str(serialized))
        self.assertNotIn("evidence_excerpt", str(serialized))
        self.assertNotIn("agent_usages", str(serialized))

    def test_maps_openalex_not_found_without_exposing_details(self):
        not_found_response = Mock(status_code=404)
        orchestrator = Mock(spec=ScientificAnalysisOrchestrator)
        orchestrator.run.side_effect = [
            requests.HTTPError(
                "private OpenAlex response",
                response=not_found_response,
            ),
            successful_run("W2"),
        ]

        response = BatchAnalysisService(orchestrator).run(
            BatchAnalysisRequest(paper_ids=["W1", "W2"])
        )

        first = response.results[0]
        self.assertEqual(first.status, "error")
        self.assertEqual(first.error.code, "paper_not_found")
        self.assertEqual(
            first.error.message,
            "La publicación no fue encontrada en OpenAlex.",
        )
        self.assertEqual(response.results[1].status, "success")

    def test_treats_insufficient_evidence_analysis_as_success(self):
        orchestrator = Mock(spec=ScientificAnalysisOrchestrator)
        orchestrator.run.side_effect = [
            SimpleNamespace(analysis=build_insufficient_analysis()),
            successful_run("W2"),
        ]

        response = BatchAnalysisService(orchestrator).run(
            BatchAnalysisRequest(paper_ids=["W1", "W2"])
        )

        self.assertEqual(response.results[0].status, "success")
        self.assertEqual(response.results[0].analysis.findings, [])
        self.assertIn(
            "Información insuficiente",
            response.results[0].analysis.objective,
        )

    def test_systemic_error_avoids_repeating_known_failed_attempts(self):
        orchestrator = Mock(spec=ScientificAnalysisOrchestrator)
        orchestrator.run.side_effect = AnalysisConfigurationError(
            "private configuration detail"
        )

        response = BatchAnalysisService(orchestrator).run(
            BatchAnalysisRequest(paper_ids=["W1", "W2", "W3"])
        )

        orchestrator.run.assert_called_once_with("W1")
        self.assertEqual(response.success_count, 0)
        self.assertEqual(response.error_count, 3)
        self.assertTrue(
            all(
                result.error.code == "analysis_not_configured"
                for result in response.results
            )
        )
        self.assertNotIn("private", response.model_dump_json())


class BatchAnalysisEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_endpoint_contract_supports_partial_success(self):
        orchestrator = Mock(spec=ScientificAnalysisOrchestrator)
        orchestrator.run.side_effect = [
            successful_run("W1"),
            AnalysisProviderError("private provider detail"),
        ]
        batch_service = BatchAnalysisService(orchestrator)

        with patch("app.main.batch_analysis_service", batch_service):
            response = self.client.post(
                "/papers/batch-analysis",
                json={"paper_ids": ["W1", "W2"]},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload),
            {
                "requested_count",
                "processed_count",
                "success_count",
                "error_count",
                "results",
            },
        )
        self.assertEqual(payload["success_count"], 1)
        self.assertEqual(payload["error_count"], 1)
        self.assertEqual(payload["results"][0]["status"], "success")
        self.assertEqual(payload["results"][0]["error"], None)
        self.assertEqual(payload["results"][1]["status"], "error")
        self.assertEqual(payload["results"][1]["analysis"], None)
        self.assertNotIn("private", response.text)

    def test_endpoint_rejects_limits_duplicates_and_invalid_id_before_work(self):
        invalid_payloads = [
            {"paper_ids": ["W1"]},
            {"paper_ids": ["W1", "W1"]},
            {"paper_ids": ["W1", "invalid"]},
            {"paper_ids": ["W1", "W2", "W3", "W4", "W5", "W6"]},
        ]
        batch_service = Mock(spec=BatchAnalysisService)

        with patch("app.main.batch_analysis_service", batch_service):
            for payload in invalid_payloads:
                with self.subTest(payload=payload):
                    response = self.client.post(
                        "/papers/batch-analysis",
                        json=payload,
                    )
                    self.assertEqual(response.status_code, 422)

        batch_service.run.assert_not_called()

    def test_batch_json_post_is_allowed_by_cors(self):
        response = self.client.options(
            "/papers/batch-analysis",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:3000",
        )
        self.assertIn(
            "content-type",
            response.headers["access-control-allow-headers"].lower(),
        )


if __name__ == "__main__":
    unittest.main()
