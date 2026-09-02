"""Deterministic retrieval and evidence-preparation component.

RetrievalAgent is named for its role in the workflow. It does not use an LLM.
"""

import re
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from app.analysis.schemas import (
    MIN_ABSTRACT_WORDS,
    PreparedScientificEvidence,
    ScientificEvidence,
)
from app.schemas import Paper
from app.services.openalex import get_paper_by_id

OPENALEX_ID_PATTERN = re.compile(r"^W\d+$")
PaperGetter = Callable[[str], dict[str, Any]]


class InvalidOpenAlexIdError(ValueError):
    pass


class InvalidPaperDataError(Exception):
    pass


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def count_abstract_words(abstract: str | None) -> int:
    if not abstract:
        return 0

    return len(re.findall(r"\b\w+\b", abstract, flags=re.UNICODE))


class RetrievalAgent:
    """Retrieve a paper and prepare its evidence using deterministic Python."""

    def __init__(self, paper_getter: PaperGetter | None = None):
        self._paper_getter = paper_getter or get_paper_by_id

    def run(self, openalex_id: str) -> PreparedScientificEvidence:
        if OPENALEX_ID_PATTERN.fullmatch(openalex_id) is None:
            raise InvalidOpenAlexIdError("The OpenAlex ID must match W followed by digits.")

        paper_data = self._paper_getter(openalex_id)

        try:
            paper = Paper.model_validate(paper_data)
        except ValidationError as error:
            raise InvalidPaperDataError from error

        abstract = _normalize_optional_string(paper.abstract)
        word_count = count_abstract_words(abstract)

        if abstract is None:
            insufficiency_reason = "missing_abstract"
        elif word_count < MIN_ABSTRACT_WORDS:
            insufficiency_reason = "abstract_too_short"
        else:
            insufficiency_reason = None

        try:
            evidence = ScientificEvidence(
                title=_normalize_optional_string(paper.title),
                abstract=abstract,
                authors=[
                    author.strip() for author in paper.authors if author.strip()
                ],
                source=_normalize_optional_string(paper.source),
                year=paper.year,
                publication_date=_normalize_optional_string(
                    paper.publication_date
                ),
                publication_type=_normalize_optional_string(
                    paper.publication_type
                ),
                doi=_normalize_optional_string(paper.doi),
            )

            return PreparedScientificEvidence(
                openalex_id=openalex_id,
                evidence=evidence,
                abstract_word_count=word_count,
                is_sufficient=insufficiency_reason is None,
                insufficiency_reason=insufficiency_reason,
            )
        except ValidationError as error:
            raise InvalidPaperDataError from error
