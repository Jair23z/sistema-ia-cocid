"""Validated local PDF storage for the development document workflow."""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile


MAX_PDF_SIZE_BYTES = 15 * 1024 * 1024
UPLOAD_CHUNK_SIZE_BYTES = 64 * 1024
MAX_PUBLIC_FILENAME_LENGTH = 120
PDF_MIME_TYPE = "application/pdf"
PDF_SIGNATURE = b"%PDF-"
DEFAULT_UPLOAD_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "uploads"


class DocumentUploadError(Exception):
    """Base exception for expected document upload failures."""


class EmptyDocumentError(DocumentUploadError):
    """The uploaded document did not contain any bytes."""


class UnsupportedDocumentError(DocumentUploadError):
    """The extension or declared MIME type is not accepted."""


class InvalidPdfSignatureError(DocumentUploadError):
    """The file does not begin with the minimum PDF signature."""


class DocumentTooLargeError(DocumentUploadError):
    """The configured upload size limit was exceeded."""


class DocumentStorageError(Exception):
    """The local storage operation failed unexpectedly."""


class DocumentNotFoundError(Exception):
    """A stored document ID has no corresponding local PDF."""


@dataclass(frozen=True)
class StoredDocument:
    document_id: UUID
    public_filename: str
    size_bytes: int
    path: Path


def sanitize_pdf_filename(filename: str | None) -> str:
    """Return safe display metadata without using it as a storage path."""
    normalized = unicodedata.normalize("NFKC", filename or "")
    basename = normalized.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    basename = "".join(character for character in basename if character.isprintable())

    if basename.casefold().endswith(".pdf"):
        basename = basename[:-4]

    safe_stem = re.sub(r"[^\w .-]+", "_", basename, flags=re.UNICODE)
    safe_stem = re.sub(r"\s+", " ", safe_stem).strip(" ._-")
    if not safe_stem:
        safe_stem = "documento"

    maximum_stem_length = MAX_PUBLIC_FILENAME_LENGTH - len(".pdf")
    safe_stem = safe_stem[:maximum_stem_length].rstrip(" ._-") or "documento"
    return f"{safe_stem}.pdf"


class DocumentStorageService:
    """Store validated PDFs under server-generated IDs only."""

    def __init__(
        self,
        upload_directory: Path = DEFAULT_UPLOAD_DIRECTORY,
        max_size_bytes: int = MAX_PDF_SIZE_BYTES,
    ):
        self._upload_directory = upload_directory.resolve()
        self._max_size_bytes = max_size_bytes

    @property
    def upload_directory(self) -> Path:
        return self._upload_directory

    def _validate_upload_metadata(self, upload: UploadFile) -> str:
        original_filename = upload.filename or ""
        if not original_filename.casefold().endswith(".pdf"):
            raise UnsupportedDocumentError("The file extension must be .pdf.")

        content_type = (upload.content_type or "").strip().casefold()
        if content_type != PDF_MIME_TYPE:
            raise UnsupportedDocumentError("The MIME type must be application/pdf.")

        return sanitize_pdf_filename(original_filename)

    def _resolve_storage_path(self, document_id: UUID, suffix: str) -> Path:
        candidate = (
            self._upload_directory / f"{document_id}{suffix}"
        ).resolve()
        try:
            candidate.relative_to(self._upload_directory)
        except ValueError as error:
            raise DocumentStorageError("Unsafe storage path.") from error
        return candidate

    @staticmethod
    def _remove_partial(partial_path: Path) -> None:
        try:
            partial_path.unlink(missing_ok=True)
        except OSError:
            pass

    async def save_pdf(self, upload: UploadFile) -> StoredDocument:
        public_filename = self._validate_upload_metadata(upload)
        document_id = uuid4()
        partial_path = self._resolve_storage_path(document_id, ".pdf.part")
        final_path = self._resolve_storage_path(document_id, ".pdf")
        size_bytes = 0
        first_chunk = True

        try:
            self._upload_directory.mkdir(parents=True, exist_ok=True)
            with partial_path.open("xb") as destination:
                while chunk := await upload.read(UPLOAD_CHUNK_SIZE_BYTES):
                    if first_chunk:
                        first_chunk = False
                        if not chunk.startswith(PDF_SIGNATURE):
                            raise InvalidPdfSignatureError(
                                "The PDF signature is missing."
                            )

                    size_bytes += len(chunk)
                    if size_bytes > self._max_size_bytes:
                        raise DocumentTooLargeError(
                            "The document exceeds the configured limit."
                        )

                    destination.write(chunk)

            if size_bytes == 0:
                raise EmptyDocumentError("The document is empty.")

            os.replace(partial_path, final_path)
            return StoredDocument(
                document_id=document_id,
                public_filename=public_filename,
                size_bytes=size_bytes,
                path=final_path,
            )
        except DocumentUploadError:
            self._remove_partial(partial_path)
            raise
        except OSError as error:
            self._remove_partial(partial_path)
            raise DocumentStorageError("Unable to store the document.") from error
        except Exception as error:
            self._remove_partial(partial_path)
            raise DocumentStorageError("Unable to store the document.") from error

    def get_document_path(self, document_id: UUID | str) -> Path:
        """Resolve a previously stored PDF for a future processing step."""
        try:
            validated_id = (
                document_id if isinstance(document_id, UUID) else UUID(document_id)
            )
        except (TypeError, ValueError, AttributeError) as error:
            raise DocumentNotFoundError("The document does not exist.") from error

        document_path = self._resolve_storage_path(validated_id, ".pdf")
        if not document_path.is_file():
            raise DocumentNotFoundError("The document does not exist.")
        return document_path
