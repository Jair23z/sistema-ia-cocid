import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError

from app.analysis.analysis_agent import AnalysisAgent
from app.analysis.orchestrator import ScientificAnalysisOrchestrator
from app.analysis.retrieval_agent import RetrievalAgent
from app.analysis.schemas import (
    AgentUsage,
    AssessedStatement,
    PreparedScientificEvidence,
    ScientificAnalysisDraft,
    ScientificEvidence,
    SupportLevel,
    VerifiedAnalysis,
    validate_evidence_excerpts,
)
from app.analysis.synthesis_agent import SynthesisAgent
from app.schemas import Paper
from app.services.scientific_analysis import (
    AnalysisInvalidResponseError,
    AnalysisProviderError,
    ScientificAnalysisLLMService,
    StructuredOutputRun,
    get_openai_configuration,
)


OBJECTIVE_EXCERPT = "This study evaluates an educational intervention."
METHODOLOGY_EXCERPT = (
    "Researchers compared two student groups using a controlled design."
)
RESULTS_EXCERPT = "The intervention group obtained higher assessment scores."
CONCLUSION_EXCERPT = (
    "The abstract suggests that the intervention may support student learning."
)
SUFFICIENT_ABSTRACT = " ".join(
    [
        OBJECTIVE_EXCERPT,
        METHODOLOGY_EXCERPT,
        RESULTS_EXCERPT,
        CONCLUSION_EXCERPT,
        "The sample and measurements are described only at an abstract level.",
        "No causal conclusion beyond the reported comparison is established.",
    ]
)


def build_paper(abstract: str | None = SUFFICIENT_ABSTRACT) -> Paper:
    return Paper(
        id="https://openalex.org/W123",
        title="A controlled educational study",
        authors=[" Ada Lovelace ", "", "Alan Turing"],
        year=2026,
        publication_date="2026-08-28",
        source=" Journal of Examples ",
        publication_type="article",
        doi="https://doi.org/10.1234/example",
        citations=42,
        openalex_id="W123",
        openalex_url="https://openalex.org/W123",
        publication_url="https://example.org/paper",
        is_open_access=True,
        open_access_status="gold",
        abstract=abstract,
    )


def prepared_evidence(*, sufficient: bool = True) -> PreparedScientificEvidence:
    abstract = SUFFICIENT_ABSTRACT if sufficient else None
    return PreparedScientificEvidence(
        openalex_id="W123",
        evidence=ScientificEvidence(
            title="A controlled educational study",
            abstract=abstract,
            authors=["Ada Lovelace", "Alan Turing"],
            source="Journal of Examples",
            year=2026,
            publication_date="2026-08-28",
            publication_type="article",
            doi="https://doi.org/10.1234/example",
        ),
        abstract_word_count=len(SUFFICIENT_ABSTRACT.split()) if sufficient else 0,
        is_sufficient=sufficient,
        insufficiency_reason=None if sufficient else "missing_abstract",
    )


def statement(
    text: str,
    support_level: SupportLevel,
    evidence_excerpt: str | None,
) -> AssessedStatement:
    return AssessedStatement(
        text=text,
        support_level=support_level,
        evidence_excerpt=evidence_excerpt,
    )


def analysis_draft() -> ScientificAnalysisDraft:
    return ScientificAnalysisDraft(
        objective=statement(
            "Evaluar una intervención educativa.",
            SupportLevel.EXPLICIT,
            OBJECTIVE_EXCERPT,
        ),
        methodology=statement(
            "Se compararon dos grupos mediante un diseño controlado.",
            SupportLevel.EXPLICIT,
            METHODOLOGY_EXCERPT,
        ),
        results=statement(
            "El grupo de intervención obtuvo puntuaciones superiores.",
            SupportLevel.EXPLICIT,
            RESULTS_EXCERPT,
        ),
        conclusion_candidate=statement(
            "La intervención demuestra que causa un mejor aprendizaje.",
            SupportLevel.REASONABLE_SYNTHESIS,
            CONCLUSION_EXCERPT,
        ),
        findings=[
            statement(
                "Se reportaron puntuaciones superiores en el grupo de intervención.",
                SupportLevel.EXPLICIT,
                RESULTS_EXCERPT,
            ),
            statement(
                "La intervención causa mejores resultados en cualquier contexto.",
                SupportLevel.REASONABLE_SYNTHESIS,
                RESULTS_EXCERPT,
            ),
        ],
    )


def verified_analysis() -> VerifiedAnalysis:
    return VerifiedAnalysis(
        objective=statement(
            "Evaluar una intervención educativa.",
            SupportLevel.EXPLICIT,
            OBJECTIVE_EXCERPT,
        ),
        methodology=statement(
            "Se compararon dos grupos mediante un diseño controlado.",
            SupportLevel.EXPLICIT,
            METHODOLOGY_EXCERPT,
        ),
        results=statement(
            "El abstract informa puntuaciones superiores para el grupo de intervención.",
            SupportLevel.EXPLICIT,
            RESULTS_EXCERPT,
        ),
        conclusions=statement(
            "El abstract sugiere prudentemente que la intervención puede apoyar el aprendizaje.",
            SupportLevel.REASONABLE_SYNTHESIS,
            CONCLUSION_EXCERPT,
        ),
        findings=[
            statement(
                "Se reportaron puntuaciones superiores en el grupo de intervención.",
                SupportLevel.EXPLICIT,
                RESULTS_EXCERPT,
            )
        ],
    )


def structured_run(
    output,
    *,
    model: str,
    input_tokens: int,
    cached_input_tokens: int,
    cache_write_tokens: int,
    output_tokens: int,
    total_tokens: int,
):
    return StructuredOutputRun(
        output=output,
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_write_tokens=cache_write_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


class InternalSchemaAndEvidenceTests(unittest.TestCase):
    def test_support_levels_and_evidence_excerpt_rules_are_strict(self):
        self.assertEqual(
            {level.value for level in SupportLevel},
            {"explicit", "reasonable_synthesis", "insufficient"},
        )

        with self.assertRaises(ValidationError):
            AssessedStatement.model_validate(
                {
                    "text": "Afirmación",
                    "support_level": "unsupported_level",
                    "evidence_excerpt": None,
                }
            )

        with self.assertRaises(ValidationError):
            statement(
                "No puede determinarse.",
                SupportLevel.INSUFFICIENT,
                OBJECTIVE_EXCERPT,
            )

        with self.assertRaises(ValidationError):
            statement("Afirmación respaldada.", SupportLevel.EXPLICIT, None)

        valid_insufficient = statement(
            "La información es insuficiente para determinarlo.",
            SupportLevel.INSUFFICIENT,
            None,
        )
        self.assertIsNone(valid_insufficient.evidence_excerpt)

    def test_evidence_excerpt_must_be_present_in_title_or_abstract(self):
        prepared = prepared_evidence()
        validate_evidence_excerpts(
            prepared.evidence,
            [
                statement(
                    "Objetivo respaldado.",
                    SupportLevel.EXPLICIT,
                    OBJECTIVE_EXCERPT,
                )
            ],
        )

        with self.assertRaises(ValueError):
            validate_evidence_excerpts(
                prepared.evidence,
                [
                    statement(
                        "Afirmación sin respaldo textual.",
                        SupportLevel.EXPLICIT,
                        "This sentence is absent from the supplied evidence.",
                    )
                ],
            )

    def test_analysis_agent_wraps_an_excerpt_not_found_in_the_evidence(self):
        draft = analysis_draft().model_copy(
            update={
                "objective": statement(
                    "Objetivo sin fragmento real.",
                    SupportLevel.EXPLICIT,
                    "An excerpt that does not exist.",
                )
            }
        )
        llm_service = Mock(spec=ScientificAnalysisLLMService)
        llm_service.run_structured.return_value = structured_run(
            draft,
            model="analysis-model",
            input_tokens=10,
            cached_input_tokens=0,
            cache_write_tokens=0,
            output_tokens=5,
            total_tokens=15,
        )

        with self.assertRaises(AnalysisInvalidResponseError):
            AnalysisAgent(llm_service).run(prepared_evidence())

    def test_synthesis_agent_wraps_an_excerpt_not_found_in_the_evidence(self):
        verified = verified_analysis().model_copy(
            update={
                "conclusions": statement(
                    "Conclusión sin fragmento real.",
                    SupportLevel.REASONABLE_SYNTHESIS,
                    "An excerpt that does not exist.",
                )
            }
        )
        llm_service = Mock(spec=ScientificAnalysisLLMService)
        llm_service.run_structured.return_value = structured_run(
            verified,
            model="synthesis-model",
            input_tokens=10,
            cached_input_tokens=0,
            cache_write_tokens=0,
            output_tokens=5,
            total_tokens=15,
        )

        with self.assertRaises(AnalysisInvalidResponseError):
            SynthesisAgent(llm_service).run(
                prepared_evidence(),
                analysis_draft(),
            )

    def test_analysis_agent_sends_only_authorized_metadata(self):
        llm_service = Mock(spec=ScientificAnalysisLLMService)
        llm_service.run_structured.return_value = structured_run(
            analysis_draft(),
            model="analysis-model",
            input_tokens=10,
            cached_input_tokens=0,
            cache_write_tokens=0,
            output_tokens=5,
            total_tokens=15,
        )

        AnalysisAgent(llm_service).run(prepared_evidence())

        payload = llm_service.run_structured.call_args.kwargs["payload"]
        self.assertEqual(
            set(payload),
            {
                "title",
                "abstract",
                "authors",
                "source",
                "year",
                "publication_date",
                "publication_type",
                "doi",
            },
        )
        self.assertNotIn("citations", payload)
        self.assertNotIn("is_open_access", payload)


class RetrievalAgentTests(unittest.TestCase):
    def test_retrieval_is_deterministic_and_selects_only_authorized_evidence(self):
        paper_getter = Mock(return_value=build_paper().model_dump())

        result = RetrievalAgent(paper_getter=paper_getter).run("W123")

        paper_getter.assert_called_once_with("W123")
        self.assertTrue(result.is_sufficient)
        self.assertEqual(result.evidence.authors, ["Ada Lovelace", "Alan Turing"])
        self.assertEqual(result.evidence.source, "Journal of Examples")
        self.assertEqual(
            set(result.evidence.model_dump()),
            {
                "title",
                "abstract",
                "authors",
                "source",
                "year",
                "publication_date",
                "publication_type",
                "doi",
            },
        )

    def test_short_abstract_is_insufficient(self):
        short_abstract = " ".join(["word"] * 39)

        result = RetrievalAgent(
            paper_getter=Mock(
                return_value=build_paper(short_abstract).model_dump()
            )
        ).run("W123")

        self.assertFalse(result.is_sufficient)
        self.assertEqual(result.abstract_word_count, 39)
        self.assertEqual(result.insufficiency_reason, "abstract_too_short")


class OrchestratorTests(unittest.TestCase):
    def build_agents(self):
        return (
            Mock(spec=RetrievalAgent),
            Mock(spec=AnalysisAgent),
            Mock(spec=SynthesisAgent),
        )

    def test_runs_in_order_makes_two_agent_calls_and_aggregates_tokens(self):
        retrieval, analysis, synthesis = self.build_agents()
        prepared = prepared_evidence()
        draft = analysis_draft()
        verified = verified_analysis()
        events: list[str] = []

        retrieval.run.side_effect = lambda openalex_id: (
            events.append("retrieval") or prepared
        )
        analysis.run.side_effect = lambda evidence: (
            events.append("analysis")
            or structured_run(
                draft,
                model="analysis-model",
                input_tokens=100,
                cached_input_tokens=10,
                cache_write_tokens=2,
                output_tokens=50,
                total_tokens=150,
            )
        )
        synthesis.run.side_effect = lambda evidence, received_draft: (
            events.append("synthesis")
            or structured_run(
                verified,
                model="synthesis-model",
                input_tokens=200,
                cached_input_tokens=20,
                cache_write_tokens=3,
                output_tokens=75,
                total_tokens=275,
            )
        )
        orchestrator = ScientificAnalysisOrchestrator(
            retrieval_agent=retrieval,
            analysis_agent=analysis,
            synthesis_agent=synthesis,
        )

        run = orchestrator.run("W123")

        self.assertEqual(events, ["retrieval", "analysis", "synthesis"])
        retrieval.run.assert_called_once_with("W123")
        analysis.run.assert_called_once_with(prepared)
        synthesis.run.assert_called_once_with(prepared, draft)
        self.assertEqual(
            run.agent_usages,
            [
                AgentUsage(
                    agent="analysis",
                    model="analysis-model",
                    input_tokens=100,
                    cached_input_tokens=10,
                    cache_write_tokens=2,
                    output_tokens=50,
                    total_tokens=150,
                ),
                AgentUsage(
                    agent="synthesis",
                    model="synthesis-model",
                    input_tokens=200,
                    cached_input_tokens=20,
                    cache_write_tokens=3,
                    output_tokens=75,
                    total_tokens=275,
                ),
            ],
        )
        self.assertEqual(run.total_input_tokens, 300)
        self.assertEqual(run.total_cached_input_tokens, 30)
        self.assertEqual(run.total_cache_write_tokens, 5)
        self.assertEqual(run.total_output_tokens, 125)
        self.assertEqual(run.total_tokens, 425)

    def test_insufficient_evidence_makes_zero_llm_agent_calls(self):
        retrieval, analysis, synthesis = self.build_agents()
        retrieval.run.return_value = prepared_evidence(sufficient=False)
        orchestrator = ScientificAnalysisOrchestrator(
            retrieval_agent=retrieval,
            analysis_agent=analysis,
            synthesis_agent=synthesis,
        )

        run = orchestrator.run("W123")

        analysis.run.assert_not_called()
        synthesis.run.assert_not_called()
        self.assertEqual(run.agent_usages, [])
        self.assertEqual(run.total_input_tokens, 0)
        self.assertEqual(run.total_output_tokens, 0)
        self.assertEqual(run.total_tokens, 0)
        self.assertEqual(run.analysis.findings, [])

    def test_analysis_failure_prevents_synthesis(self):
        retrieval, analysis, synthesis = self.build_agents()
        retrieval.run.return_value = prepared_evidence()
        analysis.run.side_effect = AnalysisProviderError("private provider detail")
        orchestrator = ScientificAnalysisOrchestrator(
            retrieval_agent=retrieval,
            analysis_agent=analysis,
            synthesis_agent=synthesis,
        )

        with self.assertRaises(AnalysisProviderError):
            orchestrator.run("W123")

        analysis.run.assert_called_once()
        synthesis.run.assert_not_called()

    def test_synthesis_failure_is_propagated_after_one_analysis_call(self):
        retrieval, analysis, synthesis = self.build_agents()
        prepared = prepared_evidence()
        draft = analysis_draft()
        retrieval.run.return_value = prepared
        analysis.run.return_value = structured_run(
            draft,
            model="analysis-model",
            input_tokens=100,
            cached_input_tokens=0,
            cache_write_tokens=0,
            output_tokens=50,
            total_tokens=150,
        )
        synthesis.run.side_effect = AnalysisProviderError(
            "private synthesis provider detail"
        )
        orchestrator = ScientificAnalysisOrchestrator(
            retrieval_agent=retrieval,
            analysis_agent=analysis,
            synthesis_agent=synthesis,
        )

        with self.assertRaises(AnalysisProviderError):
            orchestrator.run("W123")

        analysis.run.assert_called_once_with(prepared)
        synthesis.run.assert_called_once_with(prepared, draft)

    def test_verified_analysis_represents_moderation_and_removal(self):
        draft = analysis_draft()
        verified = verified_analysis()
        public = verified.to_public_analysis()

        self.assertIn("demuestra", draft.conclusion_candidate.text)
        self.assertNotIn("demuestra", public.conclusions)
        self.assertIn("sugiere", public.conclusions)
        self.assertEqual(len(draft.findings), 2)
        self.assertEqual(len(public.findings), 1)
        self.assertNotIn("cualquier contexto", " ".join(public.findings))
        self.assertEqual(
            set(public.model_dump()),
            {"objective", "methodology", "results", "conclusions", "findings"},
        )
        self.assertNotIn("evidence_excerpt", public.model_dump_json())


class ModelConfigurationTests(unittest.TestCase):
    def test_both_roles_fall_back_to_openai_model(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "base-model",
                "OPENAI_ANALYSIS_MODEL": "   ",
                "OPENAI_SYNTHESIS_MODEL": "",
            },
            clear=True,
        ):
            analysis_configuration = get_openai_configuration("analysis")
            synthesis_configuration = get_openai_configuration("synthesis")

        self.assertEqual(analysis_configuration.model, "base-model")
        self.assertEqual(synthesis_configuration.model, "base-model")

    def test_each_role_can_override_the_base_model(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "base-model",
                "OPENAI_ANALYSIS_MODEL": "analysis-override",
                "OPENAI_SYNTHESIS_MODEL": "synthesis-override",
            },
            clear=True,
        ):
            analysis_configuration = get_openai_configuration("analysis")
            synthesis_configuration = get_openai_configuration("synthesis")

        self.assertEqual(analysis_configuration.model, "analysis-override")
        self.assertEqual(synthesis_configuration.model, "synthesis-override")


class SharedProviderAdapterTests(unittest.TestCase):
    @patch("app.services.scientific_analysis.OpenAI")
    def test_reuses_one_client_for_exactly_two_requests_without_retries(
        self,
        mock_openai,
    ):
        draft = analysis_draft()
        verified = verified_analysis()
        analysis_usage = SimpleNamespace(
            input_tokens=110,
            output_tokens=60,
            total_tokens=170,
            input_tokens_details=SimpleNamespace(
                cached_tokens=11,
                cache_write_tokens=4,
            ),
        )
        synthesis_usage = SimpleNamespace(
            input_tokens=220,
            output_tokens=90,
            total_tokens=310,
            input_tokens_details=SimpleNamespace(
                cached_tokens=22,
                cache_write_tokens=6,
            ),
        )
        client = mock_openai.return_value
        client.responses.parse.side_effect = [
            SimpleNamespace(output_parsed=draft, usage=analysis_usage),
            SimpleNamespace(output_parsed=verified, usage=synthesis_usage),
        ]
        service = ScientificAnalysisLLMService()

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "base-model",
                "OPENAI_ANALYSIS_MODEL": "analysis-model",
                "OPENAI_SYNTHESIS_MODEL": "synthesis-model",
            },
            clear=True,
        ):
            analysis_result = service.run_structured(
                role="analysis",
                instructions="analysis instructions",
                payload={"abstract": SUFFICIENT_ABSTRACT},
                data_label="EVIDENCIA_CIENTIFICA",
                output_schema=ScientificAnalysisDraft,
                max_output_tokens=3000,
            )
            synthesis_result = service.run_structured(
                role="synthesis",
                instructions="synthesis instructions",
                payload={
                    "scientific_evidence": {"abstract": SUFFICIENT_ABSTRACT},
                    "analysis_draft": draft.model_dump(mode="json"),
                },
                data_label="EVIDENCIA_Y_BORRADOR",
                output_schema=VerifiedAnalysis,
                max_output_tokens=3000,
            )

        mock_openai.assert_called_once_with(
            api_key="test-key",
            timeout=30.0,
            max_retries=0,
        )
        self.assertEqual(client.responses.parse.call_count, 2)
        first_call, second_call = client.responses.parse.call_args_list
        self.assertEqual(first_call.kwargs["model"], "analysis-model")
        self.assertEqual(second_call.kwargs["model"], "synthesis-model")
        self.assertIs(
            first_call.kwargs["text_format"], ScientificAnalysisDraft
        )
        self.assertIs(second_call.kwargs["text_format"], VerifiedAnalysis)
        self.assertFalse(first_call.kwargs["store"])
        self.assertFalse(second_call.kwargs["store"])
        self.assertEqual(first_call.kwargs["tools"], [])
        self.assertEqual(second_call.kwargs["tools"], [])
        self.assertEqual(analysis_result.input_tokens, 110)
        self.assertEqual(analysis_result.cached_input_tokens, 11)
        self.assertEqual(analysis_result.cache_write_tokens, 4)
        self.assertEqual(analysis_result.output_tokens, 60)
        self.assertEqual(synthesis_result.input_tokens, 220)
        self.assertEqual(synthesis_result.cached_input_tokens, 22)
        self.assertEqual(synthesis_result.cache_write_tokens, 6)
        self.assertEqual(synthesis_result.output_tokens, 90)


if __name__ == "__main__":
    unittest.main()
