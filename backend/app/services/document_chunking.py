"""Deterministic, page-traceable chunking for extracted PDF documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from app.schemas import ChunkedDocument, DocumentChunk, ExtractedDocument
from app.services.pdf_extraction import PdfExtractionService, count_words


TARGET_WORDS = 500
OVERLAP_WORDS = 75
MIN_CHUNK_WORDS = 125
MAX_CHUNK_WORDS = 600
MIN_CHUNKABLE_WORDS = 50

PARAGRAPH_SEPARATOR = "\n\n"
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=\S)")


class DocumentChunkingError(Exception):
    """The extracted document could not be chunked consistently."""


@dataclass(frozen=True)
class TextUnit:
    page_number: int
    text: str
    starts_paragraph: bool

    @property
    def word_count(self) -> int:
        return count_words(self.text)


def _split_words(text: str, maximum_words: int) -> list[str]:
    words = re.findall(r"\S+", text)
    return [
        " ".join(words[start : start + maximum_words])
        for start in range(0, len(words), maximum_words)
    ]


def _split_long_paragraph(page_number: int, paragraph: str) -> list[TextUnit]:
    """Split only oversized paragraphs, preferring sentence boundaries."""
    sentences = [
        sentence.strip()
        for sentence in SENTENCE_BOUNDARY.split(paragraph)
        if sentence.strip()
    ]
    atomic_parts: list[str] = []
    for sentence in sentences:
        if count_words(sentence) <= MAX_CHUNK_WORDS:
            atomic_parts.append(sentence)
        else:
            atomic_parts.extend(_split_words(sentence, TARGET_WORDS))

    grouped_parts: list[str] = []
    current_parts: list[str] = []
    current_words = 0
    for part in atomic_parts:
        part_words = count_words(part)
        if current_parts and current_words + part_words > TARGET_WORDS:
            grouped_parts.append(" ".join(current_parts))
            current_parts = []
            current_words = 0
        current_parts.append(part)
        current_words += part_words

    if current_parts:
        grouped_parts.append(" ".join(current_parts))

    if (
        len(grouped_parts) > 1
        and count_words(grouped_parts[-1]) < MIN_CHUNK_WORDS
        and count_words(grouped_parts[-2]) + count_words(grouped_parts[-1])
        <= MAX_CHUNK_WORDS
    ):
        grouped_parts[-2] = f"{grouped_parts[-2]} {grouped_parts[-1]}"
        grouped_parts.pop()

    return [
        TextUnit(
            page_number=page_number,
            text=part,
            starts_paragraph=index == 0,
        )
        for index, part in enumerate(grouped_parts)
    ]


def _text_units(extracted: ExtractedDocument) -> list[TextUnit]:
    units: list[TextUnit] = []
    for page in extracted.pages:
        if not page.text.strip():
            continue
        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n{2,}", page.text)
            if paragraph.strip()
        ]
        for paragraph in paragraphs:
            if count_words(paragraph) <= MAX_CHUNK_WORDS:
                units.append(
                    TextUnit(
                        page_number=page.page_number,
                        text=paragraph,
                        starts_paragraph=True,
                    )
                )
            else:
                units.extend(_split_long_paragraph(page.page_number, paragraph))
    return units


def _unit_list_word_count(units: list[TextUnit]) -> int:
    return sum(unit.word_count for unit in units)


def _new_content_limits(chunk_index: int) -> tuple[int, int]:
    if chunk_index == 0:
        return TARGET_WORDS, MAX_CHUNK_WORDS
    return TARGET_WORDS - OVERLAP_WORDS, MAX_CHUNK_WORDS - OVERLAP_WORDS


def _should_add_unit(
    current_words: int,
    unit_words: int,
    target_words: int,
    maximum_words: int,
) -> bool:
    combined_words = current_words + unit_words
    if combined_words <= target_words:
        return True
    if combined_words > maximum_words:
        return False
    return abs(target_words - combined_words) <= abs(target_words - current_words)


def _group_new_content(units: list[TextUnit]) -> list[list[TextUnit]]:
    grouped: list[list[TextUnit]] = []
    current: list[TextUnit] = []
    current_words = 0

    for unit in units:
        target_words, maximum_words = _new_content_limits(len(grouped))
        if current and not _should_add_unit(
            current_words,
            unit.word_count,
            target_words,
            maximum_words,
        ):
            grouped.append(current)
            current = []
            current_words = 0

        current.append(unit)
        current_words += unit.word_count

    if current:
        grouped.append(current)

    if len(grouped) > 1 and _unit_list_word_count(grouped[-1]) < MIN_CHUNK_WORDS:
        previous_index = len(grouped) - 2
        _, previous_maximum = _new_content_limits(previous_index)
        if (
            _unit_list_word_count(grouped[-2])
            + _unit_list_word_count(grouped[-1])
            <= previous_maximum
        ):
            grouped[-2].extend(grouped[-1])
            grouped.pop()

    return grouped


def _tail_overlap(units: list[TextUnit], maximum_words: int) -> list[TextUnit]:
    if maximum_words <= 0:
        return []

    overlap: list[TextUnit] = []
    remaining_words = maximum_words
    for unit in reversed(units):
        if remaining_words <= 0:
            break
        if unit.word_count <= remaining_words:
            overlap.insert(0, unit)
            remaining_words -= unit.word_count
            continue

        tail_text = " ".join(re.findall(r"\S+", unit.text)[-remaining_words:])
        overlap.insert(
            0,
            TextUnit(
                page_number=unit.page_number,
                text=tail_text,
                starts_paragraph=False,
            ),
        )
        remaining_words = 0
    return overlap


def _join_units(units: list[TextUnit]) -> str:
    text = ""
    for unit in units:
        if not text:
            text = unit.text
        elif unit.starts_paragraph:
            text = f"{text}{PARAGRAPH_SEPARATOR}{unit.text}"
        else:
            text = f"{text} {unit.text}"
    return text.strip()


class DocumentChunkingService:
    """Extract and chunk a stored PDF while preserving page provenance."""

    def __init__(self, extraction_service: PdfExtractionService):
        self._extraction_service = extraction_service

    def chunk_document(self, document_id: UUID) -> ChunkedDocument:
        return self.chunk_extracted(self._extraction_service.extract(document_id))

    def chunk_extracted(self, extracted: ExtractedDocument) -> ChunkedDocument:
        units = _text_units(extracted)
        if not units or (
            extracted.requires_ocr
            and extracted.word_count < MIN_CHUNKABLE_WORDS
        ):
            return ChunkedDocument(
                document_id=extracted.document_id,
                chunk_count=0,
                total_word_count=extracted.word_count,
                chunks=[],
                requires_ocr=extracted.requires_ocr,
                status="insufficient_text",
            )

        grouped_content = _group_new_content(units)
        source_word_count = _unit_list_word_count(
            [unit for group in grouped_content for unit in group]
        )
        if source_word_count != extracted.word_count:
            raise DocumentChunkingError("Chunking changed the source word count.")

        chunks: list[DocumentChunk] = []
        previous_units: list[TextUnit] = []
        for index, new_content in enumerate(grouped_content, start=1):
            new_word_count = _unit_list_word_count(new_content)
            available_overlap = min(
                OVERLAP_WORDS,
                max(0, MAX_CHUNK_WORDS - new_word_count),
            )
            overlap = (
                _tail_overlap(previous_units, available_overlap)
                if previous_units
                else []
            )
            chunk_units = [*overlap, *new_content]
            chunk_text = _join_units(chunk_units)
            chunks.append(
                DocumentChunk(
                    document_id=extracted.document_id,
                    chunk_index=index,
                    page_start=min(unit.page_number for unit in chunk_units),
                    page_end=max(unit.page_number for unit in chunk_units),
                    text=chunk_text,
                    character_count=len(chunk_text),
                    word_count=count_words(chunk_text),
                    text_hash=sha256(chunk_text.encode("utf-8")).hexdigest(),
                )
            )
            previous_units = chunk_units

        return ChunkedDocument(
            document_id=extracted.document_id,
            chunk_count=len(chunks),
            total_word_count=extracted.word_count,
            chunks=chunks,
            requires_ocr=extracted.requires_ocr,
            status="chunked",
        )
