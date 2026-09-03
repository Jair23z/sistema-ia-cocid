"""OpenAI embeddings adapter with a bounded, process-local document cache.

The cache is intentionally temporary: it is not persisted and is lost whenever
FastAPI restarts. Its only purpose is to avoid embedding unchanged chunks more
than once during local development and the first semantic-retrieval iteration.
"""

from __future__ import annotations

import math
import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Annotated, Callable, Self
from uuid import UUID

from dotenv import load_dotenv
from openai import (
    APIError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas import ChunkedDocument, DocumentChunk


load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

DEFAULT_EMBEDDING_TIMEOUT_SECONDS = 30.0
MAX_EMBEDDING_CACHE_ENTRIES = 512


class EmbeddingConfigurationError(Exception):
    """Required embedding-provider configuration is absent."""


class EmbeddingAuthenticationError(Exception):
    """The provider rejected the configured credentials."""


class EmbeddingTimeoutError(Exception):
    """The embedding provider did not respond within the timeout."""


class EmbeddingRateLimitError(Exception):
    """The provider temporarily rejected the embedding request."""


class EmbeddingProviderError(Exception):
    """The provider could not complete an embedding request."""


class EmbeddingInvalidResponseError(Exception):
    """The provider returned unusable embeddings."""


class EmbeddingDataIntegrityError(Exception):
    """The same content hash was associated with different chunk text."""


@dataclass(frozen=True)
class EmbeddingConfiguration:
    api_key: str
    model: str


def get_embedding_configuration() -> EmbeddingConfiguration:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise EmbeddingConfigurationError("OPENAI_API_KEY is not configured.")

    model = os.getenv("OPENAI_EMBEDDING_MODEL", "").strip()
    if not model:
        raise EmbeddingConfigurationError(
            "OPENAI_EMBEDDING_MODEL is not configured."
        )

    return EmbeddingConfiguration(api_key=api_key, model=model)


InternalModelConfig = ConfigDict(extra="forbid", strict=True)
EmbeddingVector = Annotated[list[float], Field(min_length=1)]


def _validate_finite_vector(vector: list[float]) -> list[float]:
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ValueError("Embedding vectors must be non-empty and finite.")
    return vector


class EmbeddedChunk(BaseModel):
    model_config = InternalModelConfig

    chunk: DocumentChunk
    embedding_model: Annotated[str, Field(min_length=1)]
    embedding: EmbeddingVector

    @model_validator(mode="after")
    def validate_embedding(self) -> Self:
        _validate_finite_vector(self.embedding)
        return self


class EmbeddedDocument(BaseModel):
    model_config = InternalModelConfig

    document_id: UUID
    embedding_model: Annotated[str, Field(min_length=1)]
    chunks: list[EmbeddedChunk] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_consistency(self) -> Self:
        dimensions = {len(chunk.embedding) for chunk in self.chunks}
        if len(dimensions) != 1:
            raise ValueError("Document embeddings must have one dimension.")
        if any(chunk.chunk.document_id != self.document_id for chunk in self.chunks):
            raise ValueError("Every embedded chunk must belong to the document.")
        if any(
            chunk.embedding_model != self.embedding_model for chunk in self.chunks
        ):
            raise ValueError("Every chunk must use the same embedding model.")
        return self

    @property
    def dimension(self) -> int:
        return len(self.chunks[0].embedding)


class EmbeddingUsage(BaseModel):
    model_config = InternalModelConfig

    model: Annotated[str, Field(min_length=1)]
    input_tokens: Annotated[int, Field(ge=0)] | None
    request_count: Annotated[int, Field(ge=0)]


@dataclass(frozen=True)
class _CachedEmbedding:
    text: str
    vector: tuple[float, ...]


CacheKey = tuple[UUID, str, str]
OpenAIClientFactory = Callable[..., OpenAI]


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


class EmbeddingService:
    """Create embeddings and reuse unchanged document vectors in memory."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_EMBEDDING_TIMEOUT_SECONDS,
        max_cache_entries: int = MAX_EMBEDDING_CACHE_ENTRIES,
        client_factory: OpenAIClientFactory = OpenAI,
    ):
        if max_cache_entries < 1:
            raise ValueError("The embedding cache must allow at least one entry.")
        self._timeout_seconds = timeout_seconds
        self._max_cache_entries = max_cache_entries
        self._client_factory = client_factory
        self._client: OpenAI | None = None
        self._client_api_key: str | None = None
        self._cache: OrderedDict[CacheKey, _CachedEmbedding] = OrderedDict()
        self._cache_lock = Lock()

    def configuration(self) -> EmbeddingConfiguration:
        return get_embedding_configuration()

    def _get_client(self, api_key: str) -> OpenAI:
        if self._client is None or self._client_api_key != api_key:
            self._client = self._client_factory(
                api_key=api_key,
                timeout=self._timeout_seconds,
                max_retries=0,
            )
            self._client_api_key = api_key
        return self._client

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    @property
    def cache_entry_count(self) -> int:
        with self._cache_lock:
            return len(self._cache)

    def _cache_get(self, key: CacheKey, text: str) -> list[float] | None:
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is None:
                return None
            if cached.text != text:
                raise EmbeddingDataIntegrityError(
                    "A cached content hash refers to different text."
                )
            self._cache.move_to_end(key)
            return list(cached.vector)

    def _cache_set(self, key: CacheKey, text: str, vector: list[float]) -> None:
        with self._cache_lock:
            existing = self._cache.get(key)
            if existing is not None and existing.text != text:
                raise EmbeddingDataIntegrityError(
                    "A cached content hash refers to different text."
                )
            self._cache[key] = _CachedEmbedding(text=text, vector=tuple(vector))
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_cache_entries:
                self._cache.popitem(last=False)

    def _create_embeddings(
        self,
        texts: list[str],
        configuration: EmbeddingConfiguration,
    ) -> tuple[list[list[float]], EmbeddingUsage]:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingDataIntegrityError(
                "Embedding input must contain non-empty text."
            )

        client = self._get_client(configuration.api_key)
        try:
            response = client.embeddings.create(
                input=texts,
                model=configuration.model,
                encoding_format="float",
            )
        except AuthenticationError as error:
            raise EmbeddingAuthenticationError from error
        except APITimeoutError as error:
            raise EmbeddingTimeoutError from error
        except RateLimitError as error:
            raise EmbeddingRateLimitError from error
        except APIError as error:
            raise EmbeddingProviderError from error
        except OpenAIError as error:
            raise EmbeddingProviderError from error

        try:
            data = list(response.data)
            if len(data) != len(texts):
                raise ValueError("Embedding count does not match input count.")
            indexed_data = {item.index: item for item in data}
            if set(indexed_data) != set(range(len(texts))):
                raise ValueError("Embedding response indices are invalid.")

            vectors: list[list[float]] = []
            dimension: int | None = None
            for index in range(len(texts)):
                raw_vector = list(indexed_data[index].embedding)
                if any(
                    isinstance(value, bool) or not isinstance(value, (int, float))
                    for value in raw_vector
                ):
                    raise ValueError("Embedding values must be numeric.")
                vector = _validate_finite_vector(
                    [float(value) for value in raw_vector]
                )
                if dimension is None:
                    dimension = len(vector)
                elif len(vector) != dimension:
                    raise ValueError("Embedding dimensions are inconsistent.")
                vectors.append(vector)
        except (AttributeError, TypeError, ValueError) as error:
            raise EmbeddingInvalidResponseError from error

        usage = getattr(response, "usage", None)
        input_tokens = _optional_non_negative_int(
            getattr(usage, "prompt_tokens", None)
        )
        if input_tokens is None:
            input_tokens = _optional_non_negative_int(
                getattr(usage, "input_tokens", None)
            )

        return vectors, EmbeddingUsage(
            model=configuration.model,
            input_tokens=input_tokens,
            request_count=1,
        )

    def embed_document(
        self,
        document: ChunkedDocument,
        configuration: EmbeddingConfiguration,
    ) -> tuple[EmbeddedDocument, EmbeddingUsage]:
        if document.status != "chunked" or not document.chunks:
            raise EmbeddingDataIntegrityError(
                "A document without chunks cannot be embedded."
            )

        text_by_hash: dict[str, str] = {}
        vector_by_hash: dict[str, list[float]] = {}
        missing_hashes: list[str] = []
        missing_texts: list[str] = []

        for chunk in document.chunks:
            known_text = text_by_hash.get(chunk.text_hash)
            if known_text is not None and known_text != chunk.text:
                raise EmbeddingDataIntegrityError(
                    "Equal chunk hashes must refer to equal text."
                )
            if known_text is not None:
                continue
            text_by_hash[chunk.text_hash] = chunk.text

            cache_key = (
                document.document_id,
                chunk.text_hash,
                configuration.model,
            )
            cached_vector = self._cache_get(cache_key, chunk.text)
            if cached_vector is not None:
                vector_by_hash[chunk.text_hash] = cached_vector
            else:
                missing_hashes.append(chunk.text_hash)
                missing_texts.append(chunk.text)

        if missing_texts:
            new_vectors, usage = self._create_embeddings(
                missing_texts,
                configuration,
            )
            for text_hash, text, vector in zip(
                missing_hashes,
                missing_texts,
                new_vectors,
                strict=True,
            ):
                vector_by_hash[text_hash] = vector
                self._cache_set(
                    (document.document_id, text_hash, configuration.model),
                    text,
                    vector,
                )
        else:
            usage = EmbeddingUsage(
                model=configuration.model,
                input_tokens=0,
                request_count=0,
            )

        try:
            embedded_chunks = [
                EmbeddedChunk(
                    chunk=chunk,
                    embedding_model=configuration.model,
                    embedding=list(vector_by_hash[chunk.text_hash]),
                )
                for chunk in document.chunks
            ]
            embedded_document = EmbeddedDocument(
                document_id=document.document_id,
                embedding_model=configuration.model,
                chunks=embedded_chunks,
            )
        except (KeyError, ValueError) as error:
            raise EmbeddingInvalidResponseError from error
        return embedded_document, usage

    def embed_query(
        self,
        query: str,
        configuration: EmbeddingConfiguration,
        *,
        expected_dimension: int,
    ) -> tuple[list[float], EmbeddingUsage]:
        vectors, usage = self._create_embeddings([query], configuration)
        vector = vectors[0]
        if len(vector) != expected_dimension:
            raise EmbeddingInvalidResponseError(
                "Query and document embeddings have different dimensions."
            )
        return vector, usage
