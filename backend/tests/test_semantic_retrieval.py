import math
import os
import unittest
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from openai import OpenAIError
from pydantic import ValidationError

from app.main import app
from app.schemas import (
    ChunkedDocument,
    DocumentChunk,
    SemanticSearchRequest,
)
from app.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingInvalidResponseError,
    EmbeddingProviderError,
    EmbeddingService,
    get_embedding_configuration,
)
from app.services.semantic_retrieval import (
    InsufficientDocumentTextError,
    SemanticRetrievalService,
    cosine_similarity,
)


TEST_ENV = {
    "OPENAI_API_KEY": "test-key",
    "OPENAI_EMBEDDING_MODEL": "test-embedding-model",
}


def make_chunk(
    document_id: UUID,
    index: int,
    text: str,
    *,
    page_start: int | None = None,
    page_end: int | None = None,
) -> DocumentChunk:
    words = text.split()
    return DocumentChunk(
        document_id=document_id,
        chunk_index=index,
        page_start=page_start or index,
        page_end=page_end or page_start or index,
        text=text,
        character_count=len(text),
        word_count=len(words),
        text_hash=sha256(text.encode("utf-8")).hexdigest(),
    )


def make_document(
    texts: list[str],
    *,
    document_id: UUID | None = None,
    pages: list[tuple[int, int]] | None = None,
) -> ChunkedDocument:
    resolved_id = document_id or uuid4()
    chunks = [
        make_chunk(
            resolved_id,
            index,
            text,
            page_start=(pages[index - 1][0] if pages else index),
            page_end=(pages[index - 1][1] if pages else index),
        )
        for index, text in enumerate(texts, start=1)
    ]
    return ChunkedDocument(
        document_id=resolved_id,
        chunk_count=len(chunks),
        total_word_count=sum(chunk.word_count for chunk in chunks),
        chunks=chunks,
        requires_ocr=False,
        status="chunked",
    )


def insufficient_document(document_id: UUID) -> ChunkedDocument:
    return ChunkedDocument(
        document_id=document_id,
        chunk_count=0,
        total_word_count=0,
        chunks=[],
        requires_ocr=True,
        status="insufficient_text",
    )


class FakeEmbeddingsResource:
    def __init__(self, vectors_by_text: dict[str, list[float]]):
        self.vectors_by_text = vectors_by_text
        self.calls: list[dict] = []
        self.error: Exception | None = None

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        texts = list(kwargs["input"])
        data = [
            SimpleNamespace(index=index, embedding=self.vectors_by_text[text])
            for index, text in enumerate(texts)
        ]
        token_count = sum(len(text.split()) for text in texts)
        return SimpleNamespace(
            data=data,
            usage=SimpleNamespace(
                prompt_tokens=token_count,
                total_tokens=token_count,
            ),
        )


class FakeOpenAIClient:
    def __init__(self, resource: FakeEmbeddingsResource):
        self.embeddings = resource


def make_services(
    document: ChunkedDocument,
    vectors_by_text: dict[str, list[float]],
):
    resource = FakeEmbeddingsResource(vectors_by_text)
    client = FakeOpenAIClient(resource)
    embedding_service = EmbeddingService(client_factory=lambda **_: client)
    chunking_service = MagicMock()
    chunking_service.chunk_document.return_value = document
    retrieval_service = SemanticRetrievalService(
        chunking_service,
        embedding_service,
    )
    return retrieval_service, embedding_service, resource


class EmbeddingConfigurationAndCacheTests(unittest.TestCase):
    def test_embedding_model_has_no_openai_model_fallback(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "key", "OPENAI_MODEL": "not-an-embedding-model"},
            clear=True,
        ):
            with self.assertRaises(EmbeddingConfigurationError):
                get_embedding_configuration()

    def test_new_document_uses_two_calls_then_only_query(self):
        document = make_document(["methods sample", "results outcome"])
        query = "methodology"
        service, embedding_service, resource = make_services(
            document,
            {
                "methods sample": [1.0, 0.0],
                "results outcome": [0.0, 1.0],
                query: [1.0, 0.0],
            },
        )

        with patch.dict(os.environ, TEST_ENV, clear=False):
            first = service.search_document(
                document.document_id,
                SemanticSearchRequest(query=query, top_k=2),
            )
            second = service.search_document(
                document.document_id,
                SemanticSearchRequest(query=query, top_k=2),
            )

        self.assertEqual(first.usage.request_count, 2)
        self.assertEqual(second.usage.request_count, 1)
        self.assertEqual(first.usage.input_tokens, 5)
        self.assertEqual(second.usage.input_tokens, 1)
        self.assertEqual(len(resource.calls), 3)
        self.assertEqual(resource.calls[0]["input"], [
            "methods sample",
            "results outcome",
        ])
        self.assertEqual(resource.calls[1]["input"], [query])
        self.assertEqual(resource.calls[2]["input"], [query])
        self.assertEqual(embedding_service.cache_entry_count, 2)

    def test_hash_change_generates_only_the_changed_embedding(self):
        document_id = uuid4()
        first_document = make_document(
            ["unchanged text", "old text"],
            document_id=document_id,
        )
        second_document = make_document(
            ["unchanged text", "new text"],
            document_id=document_id,
        )
        resource = FakeEmbeddingsResource(
            {
                "unchanged text": [1.0, 0.0],
                "old text": [0.0, 1.0],
                "new text": [0.5, 0.5],
            }
        )
        client = FakeOpenAIClient(resource)
        embedding_service = EmbeddingService(client_factory=lambda **_: client)

        with patch.dict(os.environ, TEST_ENV, clear=False):
            configuration = embedding_service.configuration()
            embedding_service.embed_document(first_document, configuration)
            embedding_service.embed_document(second_document, configuration)

        self.assertEqual(len(resource.calls), 2)
        self.assertEqual(resource.calls[1]["input"], ["new text"])

    def test_model_change_invalidates_cached_vectors(self):
        document = make_document(["same text"])
        resource = FakeEmbeddingsResource({"same text": [1.0, 0.0]})
        client = FakeOpenAIClient(resource)
        embedding_service = EmbeddingService(client_factory=lambda **_: client)

        with patch.dict(os.environ, TEST_ENV, clear=False):
            embedding_service.embed_document(
                document,
                embedding_service.configuration(),
            )
        with patch.dict(
            os.environ,
            {**TEST_ENV, "OPENAI_EMBEDDING_MODEL": "other-model"},
            clear=False,
        ):
            embedding_service.embed_document(
                document,
                embedding_service.configuration(),
            )

        self.assertEqual(len(resource.calls), 2)
        self.assertEqual(embedding_service.cache_entry_count, 2)

    def test_duplicate_chunks_are_embedded_once_per_run(self):
        document = make_document(["duplicate text", "duplicate text"])
        resource = FakeEmbeddingsResource({"duplicate text": [1.0, 0.0]})
        client = FakeOpenAIClient(resource)
        service = EmbeddingService(client_factory=lambda **_: client)

        with patch.dict(os.environ, TEST_ENV, clear=False):
            embedded, usage = service.embed_document(
                document,
                service.configuration(),
            )

        self.assertEqual(resource.calls[0]["input"], ["duplicate text"])
        self.assertEqual(usage.request_count, 1)
        self.assertEqual(len(embedded.chunks), 2)
        self.assertEqual(embedded.chunks[0].embedding, embedded.chunks[1].embedding)


class SemanticSearchValidationTests(unittest.TestCase):
    def test_query_is_stripped_and_empty_or_oversized_queries_are_rejected(self):
        request = SemanticSearchRequest(query="  methodology  ")
        self.assertEqual(request.query, "methodology")
        for invalid_query in ("", "   ", "x" * 1001):
            with self.subTest(query_length=len(invalid_query)):
                with self.assertRaises(ValidationError):
                    SemanticSearchRequest(query=invalid_query)

    def test_top_k_accepts_one_through_eight_only(self):
        for top_k in range(1, 9):
            self.assertEqual(
                SemanticSearchRequest(query="evidence", top_k=top_k).top_k,
                top_k,
            )
        for top_k in (0, 9):
            with self.assertRaises(ValidationError):
                SemanticSearchRequest(query="evidence", top_k=top_k)

    def test_top_k_larger_than_chunk_count_returns_every_chunk(self):
        document = make_document(["one", "two"])
        service, _, _ = make_services(
            document,
            {"one": [1.0, 0.0], "two": [0.0, 1.0], "query": [1.0, 0.0]},
        )
        with patch.dict(os.environ, TEST_ENV, clear=False):
            run = service.search_document(
                document.document_id,
                SemanticSearchRequest(query="query", top_k=8),
            )
        self.assertEqual(run.response.result_count, 2)

    def test_cosine_order_tie_break_and_page_references(self):
        document = make_document(
            ["first", "second", "third"],
            pages=[(2, 3), (4, 4), (5, 6)],
        )
        service, _, _ = make_services(
            document,
            {
                "first": [1.0, 0.0],
                "second": [1.0, 0.0],
                "third": [0.0, 1.0],
                "query": [1.0, 0.0],
            },
        )
        with patch.dict(os.environ, TEST_ENV, clear=False):
            run = service.search_document(
                document.document_id,
                SemanticSearchRequest(query="query", top_k=3),
            )

        self.assertEqual(
            [result.chunk_index for result in run.response.results],
            [1, 2, 3],
        )
        self.assertEqual(
            [(result.page_start, result.page_end) for result in run.response.results],
            [(2, 3), (4, 4), (5, 6)],
        )
        self.assertTrue(all(math.isfinite(item.score) for item in run.response.results))

    def test_cosine_rejects_bad_dimensions_zero_and_non_finite_vectors(self):
        invalid_pairs = (
            ([1.0], [1.0, 2.0]),
            ([0.0, 0.0], [1.0, 0.0]),
            ([math.nan, 0.0], [1.0, 0.0]),
            ([math.inf, 0.0], [1.0, 0.0]),
        )
        for left, right in invalid_pairs:
            with self.subTest(left=left, right=right):
                with self.assertRaises(ValueError):
                    cosine_similarity(left, right)

        score = cosine_similarity([1.0, 1.0], [1.0, 1.0])
        self.assertTrue(math.isfinite(score))
        self.assertGreaterEqual(score, -1.0)
        self.assertLessEqual(score, 1.0)

    def test_query_dimension_must_match_document_dimension(self):
        document = make_document(["chunk"])
        service, _, _ = make_services(
            document,
            {"chunk": [1.0, 0.0], "query": [1.0, 0.0, 0.0]},
        )
        with patch.dict(os.environ, TEST_ENV, clear=False):
            with self.assertRaises(EmbeddingInvalidResponseError):
                service.search_document(
                    document.document_id,
                    SemanticSearchRequest(query="query"),
                )

    def test_zero_or_non_finite_provider_vectors_are_rejected(self):
        for vector, expected_error in (
            ([0.0, 0.0], ValueError),
            ([math.nan, 0.0], EmbeddingInvalidResponseError),
        ):
            document = make_document(["chunk"])
            service, _, _ = make_services(
                document,
                {"chunk": vector, "query": [1.0, 0.0]},
            )
            with self.subTest(vector=vector):
                with patch.dict(os.environ, TEST_ENV, clear=False):
                    with self.assertRaises(expected_error):
                        service.search_document(
                            document.document_id,
                            SemanticSearchRequest(query="query"),
                        )

    def test_insufficient_text_makes_zero_provider_calls(self):
        document_id = uuid4()
        service, _, resource = make_services(
            insufficient_document(document_id),
            {},
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(InsufficientDocumentTextError):
                service.search_document(
                    document_id,
                    SemanticSearchRequest(query="query"),
                )
        self.assertEqual(resource.calls, [])

    def test_provider_errors_are_translated(self):
        document = make_document(["chunk"])
        service, _, resource = make_services(
            document,
            {"chunk": [1.0, 0.0], "query": [1.0, 0.0]},
        )
        resource.error = OpenAIError("private provider detail")
        with patch.dict(os.environ, TEST_ENV, clear=False):
            with self.assertRaises(EmbeddingProviderError):
                service.search_document(
                    document.document_id,
                    SemanticSearchRequest(query="query"),
                )


class SemanticSearchEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_public_response_has_no_vectors_model_tokens_or_paths(self):
        document = make_document(
            ["methodology and sample", "other evidence"],
            pages=[(1, 2), (3, 3)],
        )
        service, _, _ = make_services(
            document,
            {
                "methodology and sample": [1.0, 0.0],
                "other evidence": [0.0, 1.0],
                "methodology": [1.0, 0.0],
            },
        )
        with (
            patch.dict(os.environ, TEST_ENV, clear=False),
            patch("app.main.semantic_retrieval_service", service),
        ):
            response = self.client.post(
                f"/documents/{document.document_id}/search",
                json={"query": "  methodology  ", "top_k": 2},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["query"], "methodology")
        self.assertEqual(payload["result_count"], 2)
        self.assertEqual(payload["results"][0]["page_start"], 1)
        self.assertEqual(payload["results"][0]["page_end"], 2)
        forbidden_terms = ("embedding", "model", "tokens", "api_key", "path")
        serialized = response.text.casefold()
        self.assertTrue(all(term not in serialized for term in forbidden_terms))

    def test_validation_and_service_errors_are_safe(self):
        document_id = uuid4()
        blank = self.client.post(
            f"/documents/{document_id}/search",
            json={"query": "   ", "top_k": 4},
        )
        invalid_top_k = self.client.post(
            f"/documents/{document_id}/search",
            json={"query": "method", "top_k": 9},
        )
        invalid_id = self.client.post(
            "/documents/not-a-uuid/search",
            json={"query": "method"},
        )

        failing_service = MagicMock()
        failing_service.search_document.side_effect = EmbeddingProviderError(
            "C:\\private\\provider-secret"
        )
        with patch("app.main.semantic_retrieval_service", failing_service):
            provider_error = self.client.post(
                f"/documents/{document_id}/search",
                json={"query": "method"},
            )

        self.assertEqual(blank.status_code, 422)
        self.assertEqual(invalid_top_k.status_code, 422)
        self.assertEqual(invalid_id.status_code, 422)
        self.assertEqual(provider_error.status_code, 502)
        self.assertEqual(
            provider_error.json()["detail"],
            "No fue posible completar la búsqueda semántica.",
        )
        self.assertNotIn("private", provider_error.text.casefold())

    def test_insufficient_text_endpoint_is_safe(self):
        service = MagicMock()
        service.search_document.side_effect = InsufficientDocumentTextError
        with patch("app.main.semantic_retrieval_service", service):
            response = self.client.post(
                f"/documents/{uuid4()}/search",
                json={"query": "method"},
            )
        self.assertEqual(response.status_code, 422)
        self.assertIn("suficiente texto", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
