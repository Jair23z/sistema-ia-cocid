"""Deterministic, page-preserving text extraction for stored PDFs."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from uuid import UUID

import pymupdf

from app.schemas import ExtractedDocument, ExtractedPage
from app.services.document_storage import DocumentStorageService


# Protect the first local implementation from pathological PDFs even though
# uploads are already limited to 15 MiB.
MAX_PDF_PAGES = 200
MIN_DOCUMENT_TEXT_CHARACTERS = 100
LOW_TEXT_PAGE_CHARACTERS = 20
LOW_TEXT_PAGE_RATIO = 0.80


class PdfExtractionError(Exception):
    """Base exception for PDFs that cannot be processed safely."""


class PdfUnreadableError(PdfExtractionError):
    """The stored file is corrupt, inaccessible, or not a processable PDF."""


class PdfEncryptedError(PdfExtractionError):
    """The PDF requires a password before its pages can be read."""


class PdfWithoutPagesError(PdfExtractionError):
    """The PDF opened but did not contain any pages."""


class PdfPageLimitExceededError(PdfExtractionError):
    """The PDF exceeds the bounded page count for this first version."""


def normalize_extracted_text(text: str) -> str:
    """Apply conservative whitespace and control-character normalization."""
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\t", " ")
    normalized = "".join(
        character
        for character in normalized
        if character == "\n" or not unicodedata.category(character).startswith("C")
    )
    normalized = re.sub(r"[^\S\n]+", " ", normalized)
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def count_non_whitespace_characters(text: str) -> int:
    return sum(not character.isspace() for character in text)


def requires_ocr_for_pages(page_texts: list[str]) -> bool:
    """Flag documents whose extractable text layer is probably insufficient."""
    text_character_counts = [
        count_non_whitespace_characters(text) for text in page_texts
    ]
    total_text_characters = sum(text_character_counts)
    if total_text_characters < MIN_DOCUMENT_TEXT_CHARACTERS:
        return True

    if len(page_texts) < 2:
        return False

    low_text_pages = sum(
        character_count < LOW_TEXT_PAGE_CHARACTERS
        for character_count in text_character_counts
    )
    return low_text_pages / len(page_texts) >= LOW_TEXT_PAGE_RATIO


class PdfExtractionService:
    """Resolve stored PDFs by UUID and extract their text without active content."""

    def __init__(self, storage_service: DocumentStorageService):
        self._storage_service = storage_service

    def extract(self, document_id: UUID) -> ExtractedDocument:
        document_path = self._storage_service.get_document_path(document_id)
        return self._extract_path(document_id, document_path)

    def _extract_path(
        self,
        document_id: UUID,
        document_path: Path,
    ) -> ExtractedDocument:
        try:
            # Reading the already size-limited file first avoids retaining an OS
            # file handle if MuPDF rejects malformed input during construction.
            with document_path.open("rb") as source:
                pdf_bytes = source.read()

            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
                if not pdf.is_pdf:
                    raise PdfUnreadableError("The stored file is not a PDF.")
                if pdf.needs_pass:
                    raise PdfEncryptedError("The PDF requires a password.")

                page_count = pdf.page_count
                if page_count < 1:
                    raise PdfWithoutPagesError("The PDF does not contain pages.")
                if page_count > MAX_PDF_PAGES:
                    raise PdfPageLimitExceededError(
                        "The PDF exceeds the configured page limit."
                    )

                page_texts = [
                    normalize_extracted_text(page.get_text("text", sort=True))
                    for page in pdf
                ]
        except PdfExtractionError:
            raise
        except (pymupdf.EmptyFileError, pymupdf.FileDataError) as error:
            raise PdfUnreadableError("The PDF cannot be read.") from error
        except (OSError, RuntimeError, ValueError) as error:
            raise PdfUnreadableError("The PDF cannot be processed.") from error

        pages = [
            ExtractedPage(
                page_number=index,
                text=text,
                character_count=len(text),
                word_count=count_words(text),
            )
            for index, text in enumerate(page_texts, start=1)
        ]
        return ExtractedDocument(
            document_id=document_id,
            page_count=len(pages),
            character_count=sum(page.character_count for page in pages),
            word_count=sum(page.word_count for page in pages),
            pages=pages,
            requires_ocr=requires_ocr_for_pages(page_texts),
            status="extracted",
        )
