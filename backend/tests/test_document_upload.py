import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.services.document_storage import (
    MAX_PDF_SIZE_BYTES,
    DocumentStorageService,
    sanitize_pdf_filename,
)


VALID_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


class DocumentUploadEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.upload_directory = Path(self.temporary_directory.name) / "uploads"
        self.storage_service = DocumentStorageService(self.upload_directory)
        self.storage_patch = patch(
            "app.main.document_storage_service",
            self.storage_service,
        )
        self.storage_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.storage_patch.stop()
        self.temporary_directory.cleanup()

    def upload(
        self,
        content: bytes,
        *,
        filename: str = "paper.pdf",
        content_type: str = "application/pdf",
    ):
        return self.client.post(
            "/documents/upload",
            files={"file": (filename, content, content_type)},
        )

    def assert_upload_directory_is_clean(self):
        if self.upload_directory.exists():
            self.assertEqual(list(self.upload_directory.iterdir()), [])

    def test_valid_pdf_is_stored_under_server_generated_uuid(self):
        response = self.upload(VALID_PDF, filename="Artículo científico.pdf")

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(
            set(payload),
            {"document_id", "filename", "size_bytes", "status"},
        )
        document_id = UUID(payload["document_id"])
        self.assertEqual(payload["filename"], "Artículo científico.pdf")
        self.assertEqual(payload["size_bytes"], len(VALID_PDF))
        self.assertEqual(payload["status"], "uploaded")
        self.assertNotIn("path", payload)

        stored_path = self.upload_directory / f"{document_id}.pdf"
        self.assertTrue(stored_path.is_file())
        self.assertEqual(stored_path.read_bytes(), VALID_PDF)
        self.assertEqual(self.storage_service.get_document_path(document_id), stored_path)
        self.assertEqual(list(self.upload_directory.glob("*.part")), [])

    def test_missing_or_empty_file_is_rejected(self):
        missing_response = self.client.post("/documents/upload")
        empty_response = self.upload(b"")

        self.assertEqual(missing_response.status_code, 422)
        self.assertEqual(empty_response.status_code, 400)
        self.assertEqual(empty_response.json()["detail"], "El archivo PDF está vacío.")
        self.assert_upload_directory_is_clean()

    def test_non_pdf_extension_is_rejected(self):
        response = self.upload(VALID_PDF, filename="paper.txt")

        self.assertEqual(response.status_code, 415)
        self.assert_upload_directory_is_clean()

    def test_incorrect_mime_is_rejected(self):
        response = self.upload(VALID_PDF, content_type="text/plain")

        self.assertEqual(response.status_code, 415)
        self.assert_upload_directory_is_clean()

    def test_missing_pdf_signature_is_rejected(self):
        response = self.upload(b"This is not a PDF.")

        self.assertEqual(response.status_code, 415)
        self.assert_upload_directory_is_clean()

    def test_pdf_larger_than_fifteen_mib_is_rejected_without_partial_file(self):
        oversized_pdf = VALID_PDF + b"0" * (
            MAX_PDF_SIZE_BYTES - len(VALID_PDF) + 1
        )

        response = self.upload(oversized_pdf)

        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            response.json()["detail"],
            "El archivo PDF supera el límite permitido de 15 MiB.",
        )
        self.assert_upload_directory_is_clean()

    def test_path_components_and_strange_characters_are_removed_from_filename(self):
        response = self.upload(
            VALID_PDF,
            filename="../../informe<>|?.pdf",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertNotIn("..", payload["filename"])
        self.assertNotIn("/", payload["filename"])
        self.assertNotIn("\\", payload["filename"])
        self.assertEqual(payload["filename"], "informe.pdf")
        stored_files = list(self.upload_directory.iterdir())
        self.assertEqual(len(stored_files), 1)
        self.assertEqual(stored_files[0].name, f'{payload["document_id"]}.pdf')

    def test_empty_sanitized_name_receives_a_safe_fallback(self):
        self.assertEqual(sanitize_pdf_filename("../.pdf"), "documento.pdf")
        self.assertEqual(sanitize_pdf_filename(None), "documento.pdf")

    def test_storage_failure_removes_partial_and_returns_safe_error(self):
        with patch(
            "app.services.document_storage.os.replace",
            side_effect=OSError("private path and operating-system detail"),
        ):
            response = self.upload(VALID_PDF)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["detail"],
            "No fue posible almacenar el documento.",
        )
        self.assertNotIn("private", response.text)
        self.assert_upload_directory_is_clean()


if __name__ == "__main__":
    unittest.main()
