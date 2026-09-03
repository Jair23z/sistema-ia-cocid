"""Deterministic Top-K retrieval over traceable PDF chunks."""

from __future__ import annotations

import math
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas import (
    RetrievedChunk,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from app.services.document_chunking import DocumentChunkingService
from app.services.embeddings import (
    EmbeddedDocument,
    EmbeddingService,
    EmbeddingUsage,
)


class InsufficientDocumentTextError(Exception):
    """The document has no useful chunks for semantic retrieval."""


def _validate_vector(vector: list[float]) -> float:
    if not vector:
        raise ValueError("Cosine similarity requires non-empty vectors.")
    if any(not math.isfinite(value) for value in vector):
        raise ValueError("Cosine similarity requires finite values.")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError("Cosine similarity requires a positive finite norm.")
    return norm


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Calculate full cosine similarity and defensively clamp round-off."""
    if len(left) != len(right):
        raise ValueError("Cosine similarity requires equal dimensions.")
    left_norm = _validate_vector(left)
    right_norm = _validate_vector(right)
    dot_product = sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=True)
    )
    score = dot_product / (left_norm * right_norm)
    if not math.isfinite(score):
        raise ValueError("Cosine similarity produced a non-finite score.")
    return max(-1.0, min(1.0, score))


class SemanticSearchRun(BaseModel):
    """Internal result including vectors and provider usage for observability."""

    model_config = ConfigDict(extra="forbid", strict=True)

    response: SemanticSearchResponse
    embedded_document: EmbeddedDocument
    query_embedding: Annotated[list[float], Field(min_length=1)]
    usage: EmbeddingUsage

    @model_validator(mode="after")
    def validate_embedding_context(self) -> Self:
        if self.usage.model != self.embedded_document.embedding_model:
            raise ValueError("Usage and document must use the same model.")
        if len(self.query_embedding) != self.embedded_document.dimension:
            raise ValueError("Query and document dimensions must match.")
        if any(not math.isfinite(value) for value in self.query_embedding):
            raise ValueError("Query embedding values must be finite.")
        return self


def _sum_input_tokens(*usage_items: EmbeddingUsage) -> int | None:
    known_values = [
        usage.input_tokens
        for usage in usage_items
        if usage.input_tokens is not None
    ]
    if not known_values:
        return None
    return sum(known_values)


class SemanticRetrievalService:
    def __init__(
        self,
        chunking_service: DocumentChunkingService,
        embedding_service: EmbeddingService,
    ):
        self._chunking_service = chunking_service
        self._embedding_service = embedding_service

    def search_document(
        self,
        document_id: UUID,
        request: SemanticSearchRequest,
    ) -> SemanticSearchRun:
        chunked_document = self._chunking_service.chunk_document(document_id)
        if (
            chunked_document.status == "insufficient_text"
            or not chunked_document.chunks
        ):
            raise InsufficientDocumentTextError

        configuration = self._embedding_service.configuration()
        embedded_document, document_usage = self._embedding_service.embed_document(
            chunked_document,
            configuration,
        )
        query_embedding, query_usage = self._embedding_service.embed_query(
            request.query,
            configuration,
            expected_dimension=embedded_document.dimension,
        )

        scored_chunks = [
            (
                cosine_similarity(query_embedding, embedded_chunk.embedding),
                embedded_chunk.chunk,
            )
            for embedded_chunk in embedded_document.chunks
        ]
        scored_chunks.sort(key=lambda item: (-item[0], item[1].chunk_index))
        selected_chunks = scored_chunks[: request.top_k]
        results = [
            RetrievedChunk(
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                text=chunk.text,
                score=float(score),
            )
            for score, chunk in selected_chunks
        ]
        response = SemanticSearchResponse(
            document_id=document_id,
            query=request.query,
            result_count=len(results),
            results=results,
            status="completed",
        )
        usage = EmbeddingUsage(
            model=configuration.model,
            input_tokens=_sum_input_tokens(document_usage, query_usage),
            request_count=(
                document_usage.request_count + query_usage.request_count
            ),
        )
        return SemanticSearchRun(
            response=response,
            embedded_document=embedded_document,
            query_embedding=query_embedding,
            usage=usage,
        )
