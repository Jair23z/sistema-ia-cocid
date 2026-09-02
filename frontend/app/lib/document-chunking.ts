import { API_BASE_URL } from "./papers";

export type DocumentChunk = {
  document_id: string;
  chunk_index: number;
  page_start: number;
  page_end: number;
  text: string;
  character_count: number;
  word_count: number;
  text_hash: string;
};

export type ChunkedDocument = {
  document_id: string;
  chunk_count: number;
  total_word_count: number;
  chunks: DocumentChunk[];
  requires_ocr: boolean;
  status: "chunked" | "insufficient_text";
};

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actualKeys = Object.keys(value);
  return (
    actualKeys.length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

function isIntegerAtLeast(value: unknown, minimum: number): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= minimum
  );
}

function isDocumentChunk(
  value: unknown,
  documentId: string,
  expectedIndex: number,
): value is DocumentChunk {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const chunk = value as Record<string, unknown>;
  return (
    hasExactKeys(chunk, [
      "document_id",
      "chunk_index",
      "page_start",
      "page_end",
      "text",
      "character_count",
      "word_count",
      "text_hash",
    ]) &&
    chunk.document_id === documentId &&
    chunk.chunk_index === expectedIndex &&
    isIntegerAtLeast(chunk.page_start, 1) &&
    isIntegerAtLeast(chunk.page_end, Number(chunk.page_start)) &&
    typeof chunk.text === "string" &&
    chunk.text.length > 0 &&
    isIntegerAtLeast(chunk.character_count, 1) &&
    isIntegerAtLeast(chunk.word_count, 1) &&
    typeof chunk.text_hash === "string" &&
    /^[0-9a-f]{64}$/.test(chunk.text_hash)
  );
}

export function isChunkedDocument(value: unknown): value is ChunkedDocument {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const document = value as Record<string, unknown>;
  if (
    !hasExactKeys(document, [
      "document_id",
      "chunk_count",
      "total_word_count",
      "chunks",
      "requires_ocr",
      "status",
    ]) ||
    typeof document.document_id !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      document.document_id,
    ) ||
    !isIntegerAtLeast(document.chunk_count, 0) ||
    !isIntegerAtLeast(document.total_word_count, 0) ||
    !Array.isArray(document.chunks) ||
    document.chunks.length !== document.chunk_count ||
    typeof document.requires_ocr !== "boolean" ||
    (document.status !== "chunked" &&
      document.status !== "insufficient_text")
  ) {
    return false;
  }

  if (
    document.status === "insufficient_text" &&
    (document.chunk_count !== 0 || document.chunks.length !== 0)
  ) {
    return false;
  }
  if (document.status === "chunked" && document.chunk_count < 1) {
    return false;
  }

  if (
    !document.chunks.every((chunk, index) =>
      isDocumentChunk(chunk, document.document_id as string, index + 1),
    )
  ) {
    return false;
  }

  const chunks = document.chunks as DocumentChunk[];
  return (
    document.status === "insufficient_text" ||
    chunks.reduce((total, chunk) => total + chunk.word_count, 0) >=
      document.total_word_count
  );
}

export async function preparePdfDocument(
  documentId: string,
  fetchImplementation: typeof fetch = fetch,
): Promise<ChunkedDocument> {
  const response = await fetchImplementation(
    `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/chunks`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    },
  );

  if (!response.ok) {
    throw new Error("document-chunking-request-failed");
  }

  const data: unknown = await response.json();
  if (!isChunkedDocument(data)) {
    throw new Error("invalid-document-chunking-response");
  }

  return data;
}
