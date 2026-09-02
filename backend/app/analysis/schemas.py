from enum import Enum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas import ScientificAnalysis


StrictModelConfig = ConfigDict(
    extra="forbid",
    frozen=True,
    strict=True,
    str_strip_whitespace=True,
)
ShortText = Annotated[str, Field(min_length=1, max_length=500)]
AnalysisText = Annotated[str, Field(min_length=1, max_length=2000)]
EvidenceExcerpt = Annotated[str, Field(min_length=1, max_length=500)]
MIN_ABSTRACT_WORDS = 40


class ScientificEvidence(BaseModel):
    """Only the publication fields authorized as input to the LLM agents."""

    model_config = StrictModelConfig

    title: Annotated[str, Field(min_length=1, max_length=1000)] | None
    abstract: Annotated[str, Field(min_length=1, max_length=50000)] | None
    authors: list[ShortText] = Field(max_length=500)
    source: Annotated[str, Field(min_length=1, max_length=1000)] | None
    year: int | None
    publication_date: Annotated[str, Field(min_length=1, max_length=50)] | None
    publication_type: Annotated[str, Field(min_length=1, max_length=200)] | None
    doi: Annotated[str, Field(min_length=1, max_length=1000)] | None


class PreparedScientificEvidence(BaseModel):
    model_config = StrictModelConfig

    openalex_id: Annotated[str, Field(pattern=r"^W\d+$")]
    evidence: ScientificEvidence
    abstract_word_count: Annotated[int, Field(ge=0)]
    is_sufficient: bool
    insufficiency_reason: Literal["missing_abstract", "abstract_too_short"] | None

    @model_validator(mode="after")
    def validate_sufficiency_state(self) -> Self:
        abstract = self.evidence.abstract

        if self.is_sufficient:
            if abstract is None or self.abstract_word_count < MIN_ABSTRACT_WORDS:
                raise ValueError("Sufficient evidence requires a usable abstract.")
            if self.insufficiency_reason is not None:
                raise ValueError(
                    "Sufficient evidence cannot have an insufficiency reason."
                )
            return self

        if self.insufficiency_reason == "missing_abstract":
            if abstract is not None or self.abstract_word_count != 0:
                raise ValueError("Missing-abstract evidence has an invalid state.")
        elif self.insufficiency_reason == "abstract_too_short":
            if abstract is None or self.abstract_word_count >= MIN_ABSTRACT_WORDS:
                raise ValueError("Short-abstract evidence has an invalid state.")
        else:
            raise ValueError("Insufficient evidence must include a valid reason.")

        return self


class SupportLevel(str, Enum):
    EXPLICIT = "explicit"
    REASONABLE_SYNTHESIS = "reasonable_synthesis"
    INSUFFICIENT = "insufficient"


class AssessedStatement(BaseModel):
    model_config = StrictModelConfig

    text: AnalysisText
    support_level: SupportLevel
    evidence_excerpt: EvidenceExcerpt | None

    @model_validator(mode="after")
    def validate_evidence_requirement(self) -> Self:
        has_evidence = self.evidence_excerpt is not None

        if self.support_level is SupportLevel.INSUFFICIENT and has_evidence:
            raise ValueError("Insufficient statements cannot include evidence excerpts.")

        if self.support_level is not SupportLevel.INSUFFICIENT and not has_evidence:
            raise ValueError("Supported statements require an evidence excerpt.")

        return self


class ScientificAnalysisDraft(BaseModel):
    model_config = StrictModelConfig

    objective: AssessedStatement
    methodology: AssessedStatement
    results: AssessedStatement
    conclusion_candidate: AssessedStatement
    findings: list[AssessedStatement] = Field(max_length=10)

    @model_validator(mode="after")
    def reject_insufficient_findings(self) -> Self:
        if any(
            finding.support_level is SupportLevel.INSUFFICIENT
            for finding in self.findings
        ):
            raise ValueError("Unsupported findings must be omitted instead of listed.")

        return self

    def assessed_statements(self) -> list[AssessedStatement]:
        return [
            self.objective,
            self.methodology,
            self.results,
            self.conclusion_candidate,
            *self.findings,
        ]


class VerifiedAnalysis(BaseModel):
    model_config = StrictModelConfig

    objective: AssessedStatement
    methodology: AssessedStatement
    results: AssessedStatement
    conclusions: AssessedStatement
    findings: list[AssessedStatement] = Field(max_length=10)

    @model_validator(mode="after")
    def reject_insufficient_findings(self) -> Self:
        if any(
            finding.support_level is SupportLevel.INSUFFICIENT
            for finding in self.findings
        ):
            raise ValueError("Unsupported findings must be removed from the final list.")

        return self

    def assessed_statements(self) -> list[AssessedStatement]:
        return [
            self.objective,
            self.methodology,
            self.results,
            self.conclusions,
            *self.findings,
        ]

    def to_public_analysis(self) -> ScientificAnalysis:
        return ScientificAnalysis(
            objective=self.objective.text,
            methodology=self.methodology.text,
            results=self.results.text,
            conclusions=self.conclusions.text,
            findings=[finding.text for finding in self.findings],
        )


class AgentUsage(BaseModel):
    model_config = StrictModelConfig

    agent: Literal["analysis", "synthesis"]
    model: Annotated[str, Field(min_length=1, max_length=200)]
    input_tokens: Annotated[int, Field(ge=0)] | None
    cached_input_tokens: Annotated[int, Field(ge=0)] | None
    cache_write_tokens: Annotated[int, Field(ge=0)] | None
    output_tokens: Annotated[int, Field(ge=0)] | None
    total_tokens: Annotated[int, Field(ge=0)] | None


class SinglePaperAnalysisRun(BaseModel):
    """Internal result designed to remain identifiable in a future batch workflow."""

    model_config = StrictModelConfig

    openalex_id: Annotated[str, Field(pattern=r"^W\d+$")]
    prepared_evidence: PreparedScientificEvidence
    draft: ScientificAnalysisDraft | None
    verified_analysis: VerifiedAnalysis | None
    analysis: ScientificAnalysis
    agent_usages: list[AgentUsage] = Field(max_length=2)
    total_input_tokens: Annotated[int, Field(ge=0)] | None
    total_cached_input_tokens: Annotated[int, Field(ge=0)] | None
    total_cache_write_tokens: Annotated[int, Field(ge=0)] | None
    total_output_tokens: Annotated[int, Field(ge=0)] | None
    total_tokens: Annotated[int, Field(ge=0)] | None

    @model_validator(mode="after")
    def validate_run_state_and_usage(self) -> Self:
        if self.prepared_evidence.openalex_id != self.openalex_id:
            raise ValueError("The prepared evidence belongs to a different paper.")

        agents = [usage.agent for usage in self.agent_usages]
        if self.prepared_evidence.is_sufficient:
            if agents != ["analysis", "synthesis"]:
                raise ValueError(
                    "Sufficient evidence requires Analysis followed by Synthesis."
                )
            if self.draft is None or self.verified_analysis is None:
                raise ValueError("A successful run requires both internal outputs.")
            if self.analysis != self.verified_analysis.to_public_analysis():
                raise ValueError("The public analysis must match the verified output.")
        elif (
            agents
            or self.draft is not None
            or self.verified_analysis is not None
        ):
            raise ValueError("Insufficient evidence cannot have LLM outputs or usage.")

        def aggregate(field: str) -> int | None:
            if not self.agent_usages:
                return 0

            values = [getattr(usage, field) for usage in self.agent_usages]
            if any(value is None for value in values):
                return None
            return sum(values)

        expected_values = {
            "total_input_tokens": aggregate("input_tokens"),
            "total_cached_input_tokens": aggregate("cached_input_tokens"),
            "total_cache_write_tokens": aggregate("cache_write_tokens"),
            "total_output_tokens": aggregate("output_tokens"),
            "total_tokens": aggregate("total_tokens"),
        }

        for field, expected_value in expected_values.items():
            if getattr(self, field) != expected_value:
                raise ValueError(f"{field} does not match the agent usage records.")

        return self


class ComparisonPaperEvidence(BaseModel):
    """Verified per-paper analysis and minimum traceability metadata."""

    model_config = StrictModelConfig

    openalex_id: Annotated[str, Field(pattern=r"^W\d+$")]
    title: Annotated[str, Field(min_length=1, max_length=1000)] | None
    doi: Annotated[str, Field(min_length=1, max_length=1000)] | None
    year: int | None
    source: Annotated[str, Field(min_length=1, max_length=1000)] | None
    analysis: ScientificAnalysis


class PreparedComparisonEvidence(BaseModel):
    model_config = StrictModelConfig

    papers: list[ComparisonPaperEvidence] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def reject_duplicate_papers(self) -> Self:
        paper_ids = [paper.openalex_id for paper in self.papers]
        if len(paper_ids) != len(set(paper_ids)):
            raise ValueError("Comparison evidence cannot contain duplicate papers.")
        return self


class ComparisonUsage(BaseModel):
    model_config = StrictModelConfig

    agent: Literal["comparison"]
    model: Annotated[str, Field(min_length=1, max_length=200)]
    input_tokens: Annotated[int, Field(ge=0)] | None
    cached_input_tokens: Annotated[int, Field(ge=0)] | None
    cache_write_tokens: Annotated[int, Field(ge=0)] | None
    output_tokens: Annotated[int, Field(ge=0)] | None
    total_tokens: Annotated[int, Field(ge=0)] | None


def validate_evidence_excerpts(
    evidence: ScientificEvidence,
    statements: list[AssessedStatement],
) -> None:
    normalized_sources = [
        " ".join(part.split()).casefold()
        for part in (evidence.title, evidence.abstract)
        if part
    ]

    for statement in statements:
        if statement.evidence_excerpt is None:
            continue

        normalized_excerpt = " ".join(
            statement.evidence_excerpt.split()
        ).casefold()
        if not any(
            normalized_excerpt in normalized_source
            for normalized_source in normalized_sources
        ):
            raise ValueError("An evidence excerpt is not present in the source text.")


def build_insufficient_analysis() -> ScientificAnalysis:
    return ScientificAnalysis(
        objective=(
            "Información insuficiente para determinar el objetivo principal "
            "con el contenido disponible."
        ),
        methodology=(
            "Información insuficiente para determinar la metodología con el "
            "contenido disponible."
        ),
        results=(
            "Información insuficiente para determinar los resultados con el "
            "contenido disponible."
        ),
        conclusions=(
            "Información insuficiente para determinar las conclusiones con el "
            "contenido disponible."
        ),
        findings=[],
    )
