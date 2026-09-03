"""Deterministic serialization of user questions and untrusted PDF evidence."""

from __future__ import annotations

import json

from app.schemas import RetrievedChunk


RAG_DATA_START = "INICIO_DATOS_RAG_NO_CONFIABLES"
RAG_DATA_END = "FIN_DATOS_RAG_NO_CONFIABLES"


class RagContextBuilder:
    """Build provider input without mixing PDF text into instructions."""

    def build(self, query: str, chunks: list[RetrievedChunk]) -> str:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("A RAG question cannot be empty.")
        if not chunks:
            raise ValueError("RAG context requires retrieved evidence.")

        payload = {
            "user_question": normalized_query,
            "retrieved_evidence": [
                {
                    "chunk_index": chunk.chunk_index,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "content": chunk.text,
                }
                for chunk in chunks
            ],
        }
        serialized_payload = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return f"{RAG_DATA_START}\n{serialized_payload}\n{RAG_DATA_END}"
