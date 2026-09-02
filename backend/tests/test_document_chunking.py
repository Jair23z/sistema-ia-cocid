import re
import unittest
from hashlib import sha256
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas import (
    ChunkedDocument,
    DocumentChunk,
    ExtractedDocument,
    ExtractedPage,
)
from app.services.document_chunking import (
    MAX_CHUNK_WORDS,
    MIN_CHUNKABLE_WORDS,
    OVERLAP_WORDS,
    TARGET_WORDS,
    DocumentChunkingService,
)
from app.services.document_storage import DocumentNotFoundError


def words(count: int, prefix: str = "word") -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


def extracted_document(
    page_texts: list[str],
    *,
    document_id: UUID | None = None,
    requires_ocr: bool = False,
) -> ExtractedDocument:
    pages = [
        ExtractedPage(
            page_number=index,
            text=text,
            character_count=len(text),
            word_count=len(re.findall(r"\S+", text)),
        )
        for index, text in enumerate(page_texts, start=1)
    ]
    return ExtractedDocument(
        document_id=document_id or uuid4(),
        page_count=len(pages),
        character_count=sum(page.character_count for page in pages),
        word_count=sum(page.word_count for page in pages),
        pages=pages,
        requires_ocr=requires_ocr,
        status="extracted",
    )


class DocumentChunkingServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = DocumentChunkingService(MagicMock())

    def test_one_page_preserves_small_paragraphs_in_one_chunk(self):
        extracted = extracted_document(
            [f"{words(80, 'first')}\n\n{words(90, 'second')}"]
        )

        result = self.service.chunk_extracted(extracted)

        self.assertEqual(result.status, "chunked")
        self.assertEqual(result.chunk_count, 1)
        chunk = result.chunks[0]
        self.assertEqual(chunk.chunk_index, 1)
        self.assertEqual((chunk.page_start, chunk.page_end), (1, 1))
        self.assertIn("\n\n", chunk.text)
        self.assertEqual(chunk.word_count, 170)
        self.assertEqual(result.total_word_count, 170)

    def test_multiple_pages_cross_with_traceable_overlap(self):
        extracted = extracted_document(
            [words(TARGET_WORDS, "page1"), words(TARGET_WORDS, "page2")]
        )

        result = self.service.chunk_extracted(extracted)

        self.assertEqual(result.chunk_count, 2)
        self.assertEqual(
            [(chunk.page_start, chunk.page_end) for chunk in result.chunks],
            [(1, 1), (1, 2)],
        )
        self.assertEqual(result.chunks[1].word_count, TARGET_WORDS + OVERLAP_WORDS)
        first_tail = result.chunks[0].text.split()[-OVERLAP_WORDS:]
        second_head = result.chunks[1].text.split()[:OVERLAP_WORDS]
        self.assertEqual(first_tail, second_head)
        self.assertEqual(result.total_word_count, TARGET_WORDS * 2)
        self.assertEqual(
            sum(chunk.word_count for chunk in result.chunks),
            result.total_word_count + OVERLAP_WORDS,
        )

    def test_long_paragraph_is_split_at_sentence_boundaries(self):
        sentences = [f"{words(100, f'sentence{index}_')}." for index in range(7)]
        extracted = extracted_document([" ".join(sentences)])

        result = self.service.chunk_extracted(extracted)

        self.assertGreater(result.chunk_count, 1)
        self.assertTrue(all(chunk.word_count <= MAX_CHUNK_WORDS for chunk in result.chunks))
        self.assertEqual(result.total_word_count, 700)

    def test_single_oversized_sentence_falls_back_to_word_boundaries(self):
        extracted = extracted_document([words(1_100, "long")])

        result = self.service.chunk_extracted(extracted)

        self.assertEqual(result.chunk_count, 2)
        self.assertTrue(all(chunk.text for chunk in result.chunks))
        self.assertTrue(all(chunk.word_count <= MAX_CHUNK_WORDS for chunk in result.chunks))

    def test_small_final_fragment_is_merged_when_maximum_allows_it(self):
        extracted = extracted_document(
            [f"{words(500, 'main')}\n\n{words(100, 'tail')}"]
        )

        result = self.service.chunk_extracted(extracted)

        self.assertEqual(result.chunk_count, 1)
        self.assertEqual(result.chunks[0].word_count, MAX_CHUNK_WORDS)

    def test_small_final_fragment_is_kept_when_merge_would_exceed_maximum(self):
        extracted = extracted_document(
            [f"{words(550, 'main')}\n\n{words(100, 'tail')}"]
        )

        result = self.service.chunk_extracted(extracted)

        self.assertEqual(result.chunk_count, 2)
        self.assertLess(result.chunks[-1].word_count, 200)
        self.assertTrue(all(chunk.word_count <= MAX_CHUNK_WORDS for chunk in result.chunks))

    def test_empty_pages_are_ignored_but_page_ranges_remain_original(self):
        extracted = extracted_document(["", words(150, "page2"), ""])

        result = self.service.chunk_extracted(extracted)

        self.assertEqual(result.chunk_count, 1)
        self.assertEqual((result.chunks[0].page_start, result.chunks[0].page_end), (2, 2))

    def test_insufficient_ocr_text_does_not_create_useless_chunks(self):
        empty_result = self.service.chunk_extracted(
            extracted_document([""], requires_ocr=True)
        )
        short_result = self.service.chunk_extracted(
            extracted_document(
                [words(MIN_CHUNKABLE_WORDS - 1)],
                requires_ocr=True,
            )
        )

        for result in (empty_result, short_result):
            self.assertEqual(result.status, "insufficient_text")
            self.assertEqual(result.chunk_count, 0)
            self.assertEqual(result.chunks, [])

    def test_ocr_flag_does_not_discard_sufficient_extracted_text(self):
        extracted = extracted_document([words(100)], requires_ocr=True)

        result = self.service.chunk_extracted(extracted)

        self.assertEqual(result.status, "chunked")
        self.assertEqual(result.chunk_count, 1)
        self.assertTrue(result.requires_ocr)

    def test_hashes_and_repeated_execution_are_identical(self):
        extracted = extracted_document(
            [words(500, "page1"), words(500, "page2")]
        )

        first = self.service.chunk_extracted(extracted)
        second = self.service.chunk_extracted(extracted)

        self.assertEqual(first, second)
        for chunk in first.chunks:
            self.assertRegex(chunk.text_hash, r"^[0-9a-f]{64}$")
            self.assertEqual(
                chunk.text_hash,
                sha256(chunk.text.encode("utf-8")).hexdigest(),
            )

    def test_schema_rejects_bad_hash_extra_fields_and_inconsistent_state(self):
        document_id = uuid4()
        text = "scientific evidence"
        with self.assertRaises(ValidationError):
            DocumentChunk(
                document_id=document_id,
                chunk_index=1,
                page_start=1,
                page_end=1,
                text=text,
                character_count=len(text),
                word_count=2,
                text_hash="0" * 64,
            )
        with self.assertRaises(ValidationError):
            ChunkedDocument(
                document_id=document_id,
                chunk_count=1,
                total_word_count=0,
                chunks=[],
                requires_ocr=True,
                status="insufficient_text",
                path="private.pdf",
            )


class DocumentChunkingEndpointTests(unittest.TestCase):
    def setUp(self):
        self.document_id = uuid4()
        self.extracted = extracted_document(
            [words(700)],
            document_id=self.document_id,
        )
        extraction_service = MagicMock()
        extraction_service.extract.return_value = self.extracted
        self.chunking_service = DocumentChunkingService(extraction_service)
        self.service_patch = patch(
            "app.main.document_chunking_service",
            self.chunking_service,
        )
        self.service_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.service_patch.stop()

    def test_endpoint_reuses_extractor_and_is_idempotent(self):
        first = self.client.post(f"/documents/{self.document_id}/chunks")
        second = self.client.post(f"/documents/{self.document_id}/chunks")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertNotIn("path", first.text.casefold())
        self.assertEqual(
            set(first.json()),
            {
                "document_id",
                "chunk_count",
                "total_word_count",
                "chunks",
                "requires_ocr",
                "status",
            },
        )

    def test_missing_and_invalid_ids_are_rejected(self):
        missing_service = MagicMock()
        missing_service.chunk_document.side_effect = DocumentNotFoundError(
            "C:\\private\\document.pdf"
        )
        with patch("app.main.document_chunking_service", missing_service):
            missing = self.client.post(f"/documents/{uuid4()}/chunks")
            invalid = self.client.post("/documents/not-a-uuid/chunks")

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"], "El documento no fue encontrado.")
        self.assertNotIn("private", missing.text)
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(missing_service.chunk_document.call_count, 1)

    def test_unexpected_errors_are_sanitized(self):
        failing_service = MagicMock()
        failing_service.chunk_document.side_effect = RuntimeError(
            "C:\\private\\document.pdf"
        )
        with patch("app.main.document_chunking_service", failing_service):
            response = self.client.post(f"/documents/{uuid4()}/chunks")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["detail"],
            "No fue posible preparar el contenido del documento.",
        )
        self.assertNotIn("private", response.text)


if __name__ == "__main__":
    unittest.main()
