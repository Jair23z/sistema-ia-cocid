import re
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class Paper(BaseModel):
    id: str | None
    title: str | None
    authors: list[str]
    year: int | None
    publication_date: str | None
    source: str | None
    publication_type: str | None
    doi: str | None
    citations: int | None
    openalex_id: str | None
    openalex_url: str | None
    publication_url: str | None
    is_open_access: bool | None
    open_access_status: str | None
    abstract: str | None


NonEmptyFinding = Annotated[str, Field(min_length=1, max_length=1000)]


class ScientificAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    objective: str = Field(min_length=1, max_length=2000)
    methodology: str = Field(min_length=1, max_length=2000)
    results: str = Field(min_length=1, max_length=2000)
    conclusions: str = Field(min_length=1, max_length=2000)
    findings: list[NonEmptyFinding] = Field(max_length=10)


BatchOpenAlexId = Annotated[str, Field(pattern=r"^W[0-9]{1,31}$")]
BatchAnalysisErrorCode = Literal[
    "paper_not_found",
    "openalex_timeout",
    "openalex_unavailable",
    "invalid_paper_data",
    "analysis_not_configured",
    "analysis_authentication_failed",
    "analysis_timeout",
    "analysis_rate_limited",
    "invalid_analysis_response",
    "analysis_unavailable",
]
BatchModelConfig = ConfigDict(
    extra="forbid",
    strict=True,
)


class BatchAnalysisRequest(BaseModel):
    """Two to five unique OpenAlex works, kept in first-occurrence order."""

    model_config = BatchModelConfig

    paper_ids: list[BatchOpenAlexId] = Field(min_length=2, max_length=5)

    @field_validator("paper_ids")
    @classmethod
    def deduplicate_ids(cls, paper_ids: list[str]) -> list[str]:
        unique_ids = list(dict.fromkeys(paper_ids))
        if len(unique_ids) < 2:
            raise ValueError("At least two unique paper IDs are required.")
        if len(unique_ids) > 5:
            raise ValueError("At most five unique paper IDs are allowed.")
        return unique_ids


class BatchAnalysisError(BaseModel):
    model_config = BatchModelConfig

    code: BatchAnalysisErrorCode
    message: str = Field(min_length=1, max_length=300)


class BatchAnalysisSuccessItem(BaseModel):
    model_config = BatchModelConfig

    openalex_id: BatchOpenAlexId
    status: Literal["success"]
    analysis: ScientificAnalysis
    error: None


class BatchAnalysisErrorItem(BaseModel):
    model_config = BatchModelConfig

    openalex_id: BatchOpenAlexId
    status: Literal["error"]
    analysis: None
    error: BatchAnalysisError


BatchPaperAnalysisResult = Annotated[
    BatchAnalysisSuccessItem | BatchAnalysisErrorItem,
    Field(discriminator="status"),
]


class BatchAnalysisResponse(BaseModel):
    model_config = BatchModelConfig

    requested_count: int = Field(
        ge=2,
        le=5,
        description="Number of unique paper IDs accepted after deduplication.",
    )
    processed_count: int = Field(
        ge=2,
        le=5,
        description="Number of unique paper IDs represented by a result item.",
    )
    success_count: int = Field(ge=0, le=5)
    error_count: int = Field(ge=0, le=5)
    results: list[BatchPaperAnalysisResult] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def validate_counts_and_results(self) -> Self:
        result_ids = [result.openalex_id for result in self.results]
        if len(result_ids) != len(set(result_ids)):
            raise ValueError("Batch results cannot contain duplicate paper IDs.")

        successful = sum(result.status == "success" for result in self.results)
        failed = len(self.results) - successful
        if (
            self.requested_count != len(self.results)
            or self.processed_count != len(self.results)
            or self.success_count != successful
            or self.error_count != failed
        ):
            raise ValueError("Batch counters do not match the result items.")

        return self


ComparisonModelConfig = ConfigDict(
    extra="forbid",
    strict=True,
    str_strip_whitespace=True,
)
ComparisonText = Annotated[str, Field(min_length=1, max_length=3000)]
ComparisonPointText = Annotated[str, Field(min_length=1, max_length=2000)]
SCOPED_GAP_PREFIXES = (
    "entre las publicaciones analizadas",
    "en el conjunto seleccionado",
    "esta muestra presenta poca evidencia sobre",
)
PROHIBITED_UNIVERSAL_CLAIM_PATTERNS = (
    re.compile(r"\b(?:nunca|jamás)\s+se\s+ha\s+(?:estudiado|investigado|analizado)\b"),
    re.compile(r"\bno\s+existen?\s+(?:estudios|investigaciones|evidencia|literatura)\b"),
    re.compile(r"\bnadie\s+ha\s+(?:investigado|estudiado|analizado)\b"),
    re.compile(
        r"\bning[uú]n(?:a)?\s+(?:estudio|investigación|publicación)\s+"
        r"(?:ha|aborda|analiza|estudia)\b"
    ),
)


class ComparativePoint(BaseModel):
    model_config = ComparisonModelConfig

    text: ComparisonPointText
    supporting_papers: list[BatchOpenAlexId] = Field(min_length=1, max_length=5)

    @field_validator("supporting_papers")
    @classmethod
    def reject_duplicate_references(cls, paper_ids: list[str]) -> list[str]:
        if len(paper_ids) != len(set(paper_ids)):
            raise ValueError("Supporting paper references cannot be duplicated.")
        return paper_ids


class ComparativeScientificAnalysis(BaseModel):
    model_config = ComparisonModelConfig

    summary: ComparisonText
    common_points: list[ComparativePoint] = Field(max_length=10)
    differences: list[ComparativePoint] = Field(max_length=10)
    trends: list[ComparativePoint] = Field(max_length=10)
    research_gaps: list[ComparativePoint] = Field(max_length=10)

    def points(self) -> list[ComparativePoint]:
        return [
            *self.common_points,
            *self.differences,
            *self.trends,
            *self.research_gaps,
        ]

    @model_validator(mode="after")
    def validate_comparative_scope(self) -> Self:
        for point in [
            *self.common_points,
            *self.differences,
            *self.trends,
        ]:
            if len(point.supporting_papers) < 2:
                raise ValueError(
                    "Comparative observations require at least two paper references."
                )

        for gap in self.research_gaps:
            normalized_gap = gap.text.casefold()
            if not normalized_gap.startswith(SCOPED_GAP_PREFIXES):
                raise ValueError(
                    "Research gaps must be explicitly limited to the analyzed set."
                )

        all_texts = [self.summary, *(point.text for point in self.points())]
        if any(
            pattern.search(text.casefold())
            for text in all_texts
            for pattern in PROHIBITED_UNIVERSAL_CLAIM_PATTERNS
        ):
            raise ValueError("The comparison contains a prohibited universal claim.")

        return self


class ComparisonPaperReference(BaseModel):
    model_config = ComparisonModelConfig

    openalex_id: BatchOpenAlexId
    title: Annotated[str, Field(min_length=1, max_length=1000)] | None
    doi: Annotated[str, Field(min_length=1, max_length=1000)] | None
    year: int | None
    source: Annotated[str, Field(min_length=1, max_length=1000)] | None


ComparisonExclusionReason = Literal["analysis_error", "insufficient_evidence"]


class ExcludedComparisonPaper(BaseModel):
    model_config = ComparisonModelConfig

    openalex_id: BatchOpenAlexId
    reason: ComparisonExclusionReason
    message: Annotated[str, Field(min_length=1, max_length=300)]
    error_code: BatchAnalysisErrorCode | None

    @model_validator(mode="after")
    def validate_error_code(self) -> Self:
        if self.reason == "analysis_error" and self.error_code is None:
            raise ValueError("Analysis errors require a public error code.")
        if self.reason == "insufficient_evidence" and self.error_code is not None:
            raise ValueError("Insufficient evidence cannot have an error code.")
        return self


class BatchComparisonResponse(BaseModel):
    model_config = ComparisonModelConfig

    batch_analysis: BatchAnalysisResponse
    comparison_status: Literal["completed", "insufficient_comparable_papers"]
    considered_count: int = Field(ge=0, le=5)
    considered_papers: list[ComparisonPaperReference] = Field(max_length=5)
    excluded_papers: list[ExcludedComparisonPaper] = Field(max_length=5)
    comparison: ComparativeScientificAnalysis | None

    @model_validator(mode="after")
    def validate_comparison_state(self) -> Self:
        considered_ids = [paper.openalex_id for paper in self.considered_papers]
        excluded_ids = [paper.openalex_id for paper in self.excluded_papers]
        batch_ids = [result.openalex_id for result in self.batch_analysis.results]

        if self.considered_count != len(considered_ids):
            raise ValueError("Considered count does not match considered papers.")
        if len(considered_ids) != len(set(considered_ids)):
            raise ValueError("Considered papers cannot be duplicated.")
        if len(excluded_ids) != len(set(excluded_ids)):
            raise ValueError("Excluded papers cannot be duplicated.")
        if set(considered_ids) & set(excluded_ids):
            raise ValueError("A paper cannot be both considered and excluded.")
        if set(considered_ids) | set(excluded_ids) != set(batch_ids):
            raise ValueError("Every batch paper must be considered or excluded.")

        if self.comparison_status == "completed":
            if self.considered_count < 2 or self.comparison is None:
                raise ValueError("A completed comparison requires at least two papers.")
        elif self.considered_count >= 2 or self.comparison is not None:
            raise ValueError(
                "Insufficient comparison status requires fewer than two papers."
            )

        if self.comparison is not None:
            allowed_ids = set(considered_ids)
            if any(
                not set(point.supporting_papers) <= allowed_ids
                for point in self.comparison.points()
            ):
                raise ValueError("The comparison references a non-considered paper.")

        return self
