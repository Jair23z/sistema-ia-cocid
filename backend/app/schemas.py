import re
from hashlib import sha256
from typing import Annotated, Literal, Self
from uuid import UUID

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


class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    document_id: UUID
    filename: Annotated[str, Field(min_length=1, max_length=120)]
    size_bytes: Annotated[int, Field(gt=0)]
    status: Literal["uploaded"]


class ExtractedPage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    page_number: Annotated[int, Field(ge=1)]
    text: str
    character_count: Annotated[int, Field(ge=0)]
    word_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def validate_page_counts(self) -> Self:
        if self.character_count != len(self.text):
            raise ValueError("Page character count does not match its text.")
        if self.word_count != len(re.findall(r"\S+", self.text)):
            raise ValueError("Page word count does not match its text.")
        return self


class ExtractedDocument(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    document_id: UUID
    page_count: Annotated[int, Field(ge=1)]
    character_count: Annotated[int, Field(ge=0)]
    word_count: Annotated[int, Field(ge=0)]
    pages: list[ExtractedPage] = Field(min_length=1)
    requires_ocr: bool
    status: Literal["extracted"]

    @model_validator(mode="after")
    def validate_document_counts(self) -> Self:
        if self.page_count != len(self.pages):
            raise ValueError("Document page count does not match its pages.")
        if [page.page_number for page in self.pages] != list(
            range(1, self.page_count + 1)
        ):
            raise ValueError("Document pages must be sequential and start at one.")
        if self.character_count != sum(
            page.character_count for page in self.pages
        ):
            raise ValueError("Document character count does not match its pages.")
        if self.word_count != sum(page.word_count for page in self.pages):
            raise ValueError("Document word count does not match its pages.")
        return self


class DocumentChunk(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    document_id: UUID
    chunk_index: Annotated[int, Field(ge=1)]
    page_start: Annotated[int, Field(ge=1)]
    page_end: Annotated[int, Field(ge=1)]
    text: Annotated[str, Field(min_length=1)]
    character_count: Annotated[int, Field(gt=0)]
    word_count: Annotated[int, Field(gt=0)]
    text_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def validate_chunk_content(self) -> Self:
        if self.page_end < self.page_start:
            raise ValueError("Chunk page range is invalid.")
        if self.character_count != len(self.text):
            raise ValueError("Chunk character count does not match its text.")
        if self.word_count != len(re.findall(r"\S+", self.text)):
            raise ValueError("Chunk word count does not match its text.")
        expected_hash = sha256(self.text.encode("utf-8")).hexdigest()
        if self.text_hash != expected_hash:
            raise ValueError("Chunk hash does not match its text.")
        return self


class ChunkedDocument(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    document_id: UUID
    chunk_count: Annotated[int, Field(ge=0)]
    total_word_count: Annotated[int, Field(ge=0)]
    chunks: list[DocumentChunk]
    requires_ocr: bool
    status: Literal["chunked", "insufficient_text"]

    @model_validator(mode="after")
    def validate_chunking_state(self) -> Self:
        if self.chunk_count != len(self.chunks):
            raise ValueError("Chunk count does not match the chunk list.")
        if self.status == "insufficient_text":
            if self.chunk_count != 0 or self.chunks:
                raise ValueError("Insufficient text cannot contain chunks.")
            return self

        if not self.chunks:
            raise ValueError("A chunked document must contain at least one chunk.")
        if [chunk.chunk_index for chunk in self.chunks] != list(
            range(1, self.chunk_count + 1)
        ):
            raise ValueError("Chunk indices must be consecutive and start at one.")
        if any(chunk.document_id != self.document_id for chunk in self.chunks):
            raise ValueError("Every chunk must belong to the same document.")
        if self.total_word_count > sum(chunk.word_count for chunk in self.chunks):
            raise ValueError("Chunk words cannot omit source document words.")
        return self


SemanticQuery = Annotated[str, Field(min_length=1, max_length=1000)]


class SemanticSearchRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    query: SemanticQuery
    top_k: Annotated[int, Field(ge=1, le=8)] = 4

    @field_validator("query")
    @classmethod
    def normalize_query(cls, query: str) -> str:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("The semantic-search query cannot be empty.")
        return normalized_query


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    document_id: UUID
    chunk_index: Annotated[int, Field(ge=1)]
    page_start: Annotated[int, Field(ge=1)]
    page_end: Annotated[int, Field(ge=1)]
    text: Annotated[str, Field(min_length=1)]
    score: Annotated[float, Field(ge=-1.0, le=1.0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def validate_page_range(self) -> Self:
        if self.page_end < self.page_start:
            raise ValueError("Retrieved chunk page range is invalid.")
        return self


class SemanticSearchResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    document_id: UUID
    query: SemanticQuery
    result_count: Annotated[int, Field(ge=0, le=8)]
    results: list[RetrievedChunk] = Field(max_length=8)
    status: Literal["completed"]

    @model_validator(mode="after")
    def validate_results(self) -> Self:
        if self.result_count != len(self.results):
            raise ValueError("Semantic-search result count does not match results.")
        if any(result.document_id != self.document_id for result in self.results):
            raise ValueError("Every result must belong to the searched document.")
        return self


EvidenceStatus = Literal["sufficient", "partial", "insufficient"]
INSUFFICIENT_DOCUMENT_EVIDENCE_MESSAGE = (
    "No existe evidencia suficiente en los fragmentos recuperados para "
    "responder esta pregunta."
)


class DocumentQuestionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    query: SemanticQuery
    top_k: Annotated[int, Field(ge=1, le=8)] = 4

    @field_validator("query")
    @classmethod
    def normalize_query(cls, query: str) -> str:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("The document question cannot be empty.")
        return normalized_query


class DocumentCitation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    chunk_index: Annotated[int, Field(ge=1)]
    page_start: Annotated[int, Field(ge=1)]
    page_end: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def validate_page_range(self) -> Self:
        if self.page_end < self.page_start:
            raise ValueError("Document citation page range is invalid.")
        return self


class DocumentAnswerResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    document_id: UUID
    query: SemanticQuery
    answer: Annotated[str, Field(min_length=1, max_length=6000)]
    evidence_status: EvidenceStatus
    citations: list[DocumentCitation] = Field(max_length=8)
    status: Literal["completed"]

    @model_validator(mode="after")
    def validate_evidence_state(self) -> Self:
        citation_keys = [
            (citation.chunk_index, citation.page_start, citation.page_end)
            for citation in self.citations
        ]
        if len(citation_keys) != len(set(citation_keys)):
            raise ValueError("Document citations cannot be duplicated.")

        if self.evidence_status == "insufficient":
            if self.citations:
                raise ValueError("Insufficient evidence cannot include citations.")
            if self.answer != INSUFFICIENT_DOCUMENT_EVIDENCE_MESSAGE:
                raise ValueError("Insufficient evidence must use the safe response.")
        elif not self.citations:
            raise ValueError("Supported document answers require citations.")
        return self


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
