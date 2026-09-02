"""Sequential orchestration for one publication's scientific analysis."""

from app.analysis.analysis_agent import AnalysisAgent
from app.analysis.retrieval_agent import RetrievalAgent
from app.analysis.schemas import (
    AgentUsage,
    SinglePaperAnalysisRun,
    build_insufficient_analysis,
)
from app.analysis.synthesis_agent import SynthesisAgent
from app.services.scientific_analysis import (
    ScientificAnalysisLLMService,
    StructuredOutputRun,
)


def _agent_usage(
    agent: str,
    result: StructuredOutputRun,
) -> AgentUsage:
    return AgentUsage(
        agent=agent,
        model=result.model,
        input_tokens=result.input_tokens,
        cached_input_tokens=result.cached_input_tokens,
        cache_write_tokens=result.cache_write_tokens,
        output_tokens=result.output_tokens,
        total_tokens=result.total_tokens,
    )


def _aggregate_usage(usages: list[AgentUsage], field: str) -> int | None:
    values = [getattr(usage, field) for usage in usages]
    if any(value is None for value in values):
        return None
    return sum(values)


class ScientificAnalysisOrchestrator:
    """Run Retrieval, Analysis and Synthesis in a fixed fail-fast order."""

    def __init__(
        self,
        *,
        retrieval_agent: RetrievalAgent | None = None,
        analysis_agent: AnalysisAgent | None = None,
        synthesis_agent: SynthesisAgent | None = None,
        llm_service: ScientificAnalysisLLMService | None = None,
    ):
        shared_llm_service = llm_service or ScientificAnalysisLLMService()
        self._retrieval_agent = retrieval_agent or RetrievalAgent()
        self._analysis_agent = analysis_agent or AnalysisAgent(shared_llm_service)
        self._synthesis_agent = synthesis_agent or SynthesisAgent(shared_llm_service)

    def run(self, openalex_id: str) -> SinglePaperAnalysisRun:
        prepared_evidence = self._retrieval_agent.run(openalex_id)

        if not prepared_evidence.is_sufficient:
            analysis = build_insufficient_analysis()
            return SinglePaperAnalysisRun(
                openalex_id=openalex_id,
                prepared_evidence=prepared_evidence,
                draft=None,
                verified_analysis=None,
                analysis=analysis,
                agent_usages=[],
                total_input_tokens=0,
                total_cached_input_tokens=0,
                total_cache_write_tokens=0,
                total_output_tokens=0,
                total_tokens=0,
            )

        analysis_result = self._analysis_agent.run(prepared_evidence)
        synthesis_result = self._synthesis_agent.run(
            prepared_evidence,
            analysis_result.output,
        )
        verified_analysis = synthesis_result.output
        agent_usages = [
            _agent_usage("analysis", analysis_result),
            _agent_usage("synthesis", synthesis_result),
        ]

        return SinglePaperAnalysisRun(
            openalex_id=openalex_id,
            prepared_evidence=prepared_evidence,
            draft=analysis_result.output,
            verified_analysis=verified_analysis,
            analysis=verified_analysis.to_public_analysis(),
            agent_usages=agent_usages,
            total_input_tokens=_aggregate_usage(agent_usages, "input_tokens"),
            total_cached_input_tokens=_aggregate_usage(
                agent_usages,
                "cached_input_tokens",
            ),
            total_cache_write_tokens=_aggregate_usage(
                agent_usages,
                "cache_write_tokens",
            ),
            total_output_tokens=_aggregate_usage(agent_usages, "output_tokens"),
            total_tokens=_aggregate_usage(agent_usages, "total_tokens"),
        )
