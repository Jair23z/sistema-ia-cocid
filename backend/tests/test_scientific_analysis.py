import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient
from openai import APIConnectionError
from pydantic import ValidationError

from app.main import app
from app.schemas import ScientificAnalysis
from app.services.scientific_analysis import (
    AnalysisConfigurationError,
    AnalysisInvalidResponseError,
    AnalysisProviderError,
    ScientificAnalysisLLMService,
)


def valid_analysis() -> ScientificAnalysis:
    return ScientificAnalysis(
        objective="Objetivo sustentado.",
        methodology="Metodología sustentada.",
        results="Resultados sustentados.",
        conclusions="Conclusión prudente.",
        findings=["Hallazgo sustentado."],
    )


def provider_response(output=None):
    return SimpleNamespace(
        output_parsed=output or valid_analysis(),
        usage=SimpleNamespace(
            input_tokens=120,
            input_tokens_details=SimpleNamespace(
                cached_tokens=20,
                cache_write_tokens=10,
            ),
            output_tokens=80,
            total_tokens=200,
        ),
    )


class ScientificAnalysisSchemaTests(unittest.TestCase):
    def test_public_schema_remains_strict_about_shape_and_content(self):
        with self.assertRaises(ValidationError):
            ScientificAnalysis(
                objective=" ",
                methodology="Método",
                results="Resultados",
                conclusions="Conclusiones",
                findings=[],
            )

        with self.assertRaises(ValidationError):
            ScientificAnalysis.model_validate(
                {
                    **valid_analysis().model_dump(),
                    "unexpected": "No permitido",
                }
            )

        with self.assertRaises(ValidationError):
            ScientificAnalysis(
                objective="Objetivo",
                methodology="Método",
                results="Resultados",
                conclusions="Conclusiones",
                findings=["Hallazgo"] * 11,
            )


class SharedLLMServiceTests(unittest.TestCase):
    @patch("app.services.scientific_analysis.OpenAI")
    def test_reuses_one_client_and_applies_fallback_models(self, mock_openai):
        client = mock_openai.return_value
        client.responses.parse.return_value = provider_response()
        service = ScientificAnalysisLLMService(timeout_seconds=12.0)

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "fallback-model",
                "OPENAI_ANALYSIS_MODEL": "",
                "OPENAI_SYNTHESIS_MODEL": "",
            },
            clear=True,
        ):
            analysis_run = service.run_structured(
                role="analysis",
                instructions="analysis prompt",
                payload={"title": "Paper"},
                data_label="EVIDENCIA",
                output_schema=ScientificAnalysis,
                max_output_tokens=1000,
            )
            synthesis_run = service.run_structured(
                role="synthesis",
                instructions="synthesis prompt",
                payload={"draft": "data"},
                data_label="BORRADOR",
                output_schema=ScientificAnalysis,
                max_output_tokens=1000,
            )

        mock_openai.assert_called_once_with(
            api_key="test-key",
            timeout=12.0,
            max_retries=0,
        )
        self.assertEqual(client.responses.parse.call_count, 2)
        self.assertEqual(analysis_run.model, "fallback-model")
        self.assertEqual(synthesis_run.model, "fallback-model")
        self.assertEqual(analysis_run.input_tokens, 120)
        self.assertEqual(analysis_run.cached_input_tokens, 20)
        self.assertEqual(analysis_run.cache_write_tokens, 10)
        self.assertEqual(analysis_run.output_tokens, 80)
        self.assertEqual(analysis_run.total_tokens, 200)

        for provider_call in client.responses.parse.call_args_list:
            kwargs = provider_call.kwargs
            self.assertEqual(kwargs["model"], "fallback-model")
            self.assertFalse(kwargs["store"])
            self.assertEqual(kwargs["tools"], [])

    @patch("app.services.scientific_analysis.OpenAI")
    def test_individual_model_overrides(self, mock_openai):
        mock_openai.return_value.responses.parse.return_value = provider_response()
        service = ScientificAnalysisLLMService()

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "fallback-model",
                "OPENAI_ANALYSIS_MODEL": "analysis-model",
                "OPENAI_SYNTHESIS_MODEL": "synthesis-model",
            },
            clear=True,
        ):
            first = service.run_structured(
                role="analysis",
                instructions="prompt",
                payload={},
                data_label="DATA",
                output_schema=ScientificAnalysis,
                max_output_tokens=1000,
            )
            second = service.run_structured(
                role="synthesis",
                instructions="prompt",
                payload={},
                data_label="DATA",
                output_schema=ScientificAnalysis,
                max_output_tokens=1000,
            )

        self.assertEqual(first.model, "analysis-model")
        self.assertEqual(second.model, "synthesis-model")

    @patch("app.services.scientific_analysis.OpenAI")
    def test_rejects_malformed_output(self, mock_openai):
        mock_openai.return_value.responses.parse.return_value = provider_response(
            {"objective": "incomplete"}
        )

        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "test-model"},
            clear=True,
        ):
            with self.assertRaises(AnalysisInvalidResponseError):
                ScientificAnalysisLLMService().run_structured(
                    role="analysis",
                    instructions="prompt",
                    payload={},
                    data_label="DATA",
                    output_schema=ScientificAnalysis,
                    max_output_tokens=1000,
                )

    @patch("app.services.scientific_analysis.OpenAI")
    def test_wraps_provider_error(self, mock_openai):
        mock_openai.return_value.responses.parse.side_effect = APIConnectionError(
            request=Mock()
        )

        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "test-model"},
            clear=True,
        ):
            with self.assertRaises(AnalysisProviderError):
                ScientificAnalysisLLMService().run_structured(
                    role="analysis",
                    instructions="prompt",
                    payload={},
                    data_label="DATA",
                    output_schema=ScientificAnalysis,
                    max_output_tokens=1000,
                )

    def test_requires_api_key_and_model(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AnalysisConfigurationError):
                ScientificAnalysisLLMService().run_structured(
                    role="analysis",
                    instructions="prompt",
                    payload={},
                    data_label="DATA",
                    output_schema=ScientificAnalysis,
                    max_output_tokens=1000,
                )

        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key"},
            clear=True,
        ):
            with self.assertRaises(AnalysisConfigurationError):
                ScientificAnalysisLLMService().run_structured(
                    role="synthesis",
                    instructions="prompt",
                    payload={},
                    data_label="DATA",
                    output_schema=ScientificAnalysis,
                    max_output_tokens=1000,
                )


class AnalysisEndpointCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.main.scientific_analysis_orchestrator")
    def test_endpoint_keeps_exact_public_response(self, orchestrator):
        orchestrator.run.return_value = SimpleNamespace(analysis=valid_analysis())

        response = self.client.post("/papers/W123/analysis")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), valid_analysis().model_dump())
        self.assertEqual(
            set(response.json()),
            {"objective", "methodology", "results", "conclusions", "findings"},
        )
        orchestrator.run.assert_called_once_with("W123")

    @patch("app.main.scientific_analysis_orchestrator")
    def test_returns_404_when_publication_does_not_exist(self, orchestrator):
        response_404 = Mock()
        response_404.status_code = 404
        orchestrator.run.side_effect = requests.HTTPError(response=response_404)

        response = self.client.post("/papers/W999/analysis")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"detail": "La publicación no fue encontrada en OpenAlex."},
        )

    @patch("app.main.scientific_analysis_orchestrator")
    def test_does_not_expose_provider_error_details(self, orchestrator):
        orchestrator.run.side_effect = AnalysisProviderError(
            "sensitive provider detail"
        )

        response = self.client.post("/papers/W123/analysis")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(),
            {"detail": "No fue posible completar el análisis científico."},
        )
        self.assertNotIn("sensitive", response.text)


if __name__ == "__main__":
    unittest.main()
