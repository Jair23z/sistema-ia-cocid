import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pymupdf
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas import ExtractedDocument, ExtractedPage
from app.services.document_storage import DocumentStorageService
from app.services.pdf_extraction import (
    MAX_PDF_PAGES,
    PdfExtractionService,
    PdfUnreadableError,
    normalize_extracted_text,
)


PAGE_TEXT = (
    "Scientific evidence is presented on this page.\n"
    "The deterministic extraction preserves its page provenance.\n"
    "Results remain associated with the original document."
)


def create_pdf(page_texts: list[str | None], *, encrypted: bool = False) -> bytes:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=10)

    save_options = {}
    if encrypted:
        save_options = {
            "encryption": pymupdf.PDF_ENCRYPT_AES_256,
            "owner_pw": "owner-secret",
            "user_pw": "user-secret",
        }

    content = document.tobytes(**save_options)
    document.close()
    return content


class PdfExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.upload_directory = Path(self.temporary_directory.name) / "uploads"
        self.storage_service = DocumentStorageService(self.upload_directory)
        self.extraction_service = PdfExtractionService(self.storage_service)
        self.extractor_patch = patch(
            "app.main.pdf_extraction_service",
            self.extraction_service,
        )
        self.extractor_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.extractor_patch.stop()
        self.temporary_directory.cleanup()

    def store_pdf(self, content: bytes) -> UUID:
        document_id = uuid4()
        self.upload_directory.mkdir(parents=True, exist_ok=True)
        (self.upload_directory / f"{document_id}.pdf").write_bytes(content)
        return document_id

    def extract(self, document_id: UUID | str):
        return self.client.post(f"/documents/{document_id}/extract")

    def test_single_page_pdf_returns_page_text_and_consistent_counts(self):
        document_id = self.store_pdf(create_pdf([PAGE_TEXT]))

        response = self.extract(document_id)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload),
            {
                "document_id",
                "page_count",
                "character_count",
                "word_count",
                "pages",
                "requires_ocr",
                "status",
            },
        )
        self.assertEqual(payload["document_id"], str(document_id))
        self.assertEqual(payload["page_count"], 1)
        self.assertEqual(payload["status"], "extracted")
        self.assertFalse(payload["requires_ocr"])
        self.assertIn("Scientific evidence", payload["pages"][0]["text"])
        self.assertEqual(payload["pages"][0]["page_number"], 1)
        self.assertEqual(
            payload["character_count"],
            payload["pages"][0]["character_count"],
        )
        self.assertEqual(payload["word_count"], payload["pages"][0]["word_count"])
        self.assertNotIn("path", payload)
        self.assertNotIn(str(self.upload_directory), response.text)

    def test_multiple_pages_preserve_order_and_aggregate_counts(self):
        document_id = self.store_pdf(
            create_pdf([PAGE_TEXT, PAGE_TEXT.replace("Scientific", "Academic")])
        )

        response = self.extract(document_id)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page_count"], 2)
        self.assertEqual(
            [page["page_number"] for page in payload["pages"]],
            [1, 2],
        )
        self.assertEqual(
            payload["character_count"],
            sum(page["character_count"] for page in payload["pages"]),
        )
        self.assertEqual(
            payload["word_count"],
            sum(page["word_count"] for page in payload["pages"]),
        )
        self.assertFalse(payload["requires_ocr"])

    def test_empty_page_is_preserved_without_inventing_text(self):
        document_id = self.store_pdf(create_pdf([PAGE_TEXT, None]))

        response = self.extract(document_id)

        self.assertEqual(response.status_code, 200)
        empty_page = response.json()["pages"][1]
        self.assertEqual(empty_page["text"], "")
        self.assertEqual(empty_page["character_count"], 0)
        self.assertEqual(empty_page["word_count"], 0)

    def test_text_normalization_is_conservative_and_deterministic(self):
        raw_text = "  Cafe\u0301\t cienti\u0000fico  \r\n\r\n\r\nResultado   final.  \r"

        normalized = normalize_extracted_text(raw_text)

        self.assertEqual(normalized, "Café cientifico\n\nResultado final.")

    def test_missing_and_invalid_document_ids_are_rejected(self):
        missing_response = self.extract(uuid4())
        invalid_response = self.extract("not-a-uuid")

        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(missing_response.json()["detail"], "El documento no fue encontrado.")
        self.assertEqual(invalid_response.status_code, 422)

    def test_corrupt_pdf_returns_safe_unprocessable_error(self):
        document_id = self.store_pdf(b"%PDF-1.4\ncorrupt private data")

        response = self.extract(document_id)

        self.assertEqual(response.status_code, 422)
        self.assertNotIn(str(self.upload_directory), response.text)
        self.assertNotIn("private data", response.text)

    def test_empty_text_document_succeeds_and_requires_ocr(self):
        document_id = self.store_pdf(create_pdf([None]))

        response = self.extract(document_id)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["requires_ocr"])
        self.assertEqual(payload["character_count"], 0)
        self.assertEqual(payload["word_count"], 0)
        self.assertEqual(payload["pages"][0]["text"], "")

    def test_eighty_percent_low_text_pages_require_ocr(self):
        document_id = self.store_pdf(
            create_pdf([PAGE_TEXT, None, None, None, None])
        )

        response = self.extract(document_id)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["requires_ocr"])

    def test_pdf_over_page_limit_is_rejected_before_page_extraction(self):
        document_id = self.store_pdf(create_pdf([None] * (MAX_PDF_PAGES + 1)))

        response = self.extract(document_id)

        self.assertEqual(response.status_code, 422)
        self.assertIn(str(MAX_PDF_PAGES), response.json()["detail"])

    def test_encrypted_pdf_is_rejected_safely(self):
        document_id = self.store_pdf(create_pdf([PAGE_TEXT], encrypted=True))

        response = self.extract(document_id)

        self.assertEqual(response.status_code, 422)
        self.assertIn("cifrado", response.json()["detail"])
        self.assertNotIn("secret", response.text)

    def test_document_without_pages_is_rejected(self):
        empty_document = MagicMock()
        empty_document.__enter__.return_value = empty_document
        empty_document.__exit__.return_value = False
        empty_document.is_pdf = True
        empty_document.needs_pass = False
        empty_document.page_count = 0
        document_id = self.store_pdf(create_pdf([None]))

        with patch("app.services.pdf_extraction.pymupdf.open", return_value=empty_document):
            response = self.extract(document_id)

        self.assertEqual(response.status_code, 422)

    def test_internal_errors_are_sanitized_and_do_not_expose_paths(self):
        private_detail = str(self.upload_directory / "private.pdf")
        with patch(
            "app.main.pdf_extraction_service.extract",
            side_effect=RuntimeError(private_detail),
        ):
            response = self.extract(uuid4())

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["detail"],
            "No fue posible extraer el contenido del documento.",
        )
        self.assertNotIn(private_detail, response.text)

    def test_strict_schemas_reject_extra_fields_and_inconsistent_counts(self):
        page = ExtractedPage(
            page_number=1,
            text="evidence",
            character_count=8,
            word_count=1,
        )

        with self.assertRaises(ValidationError):
            ExtractedDocument(
                document_id=uuid4(),
                page_count=2,
                character_count=8,
                word_count=1,
                pages=[page],
                requires_ocr=True,
                status="extracted",
            )
        with self.assertRaises(ValidationError):
            ExtractedPage(
                page_number=1,
                text="evidence",
                character_count=8,
                word_count=1,
                unexpected=True,
            )


if __name__ == "__main__":
    unittest.main()
