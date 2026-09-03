import { API_BASE_URL } from "./papers";

export const DEFAULT_SEMANTIC_TOP_K = 4;
export const MAX_SEMANTIC_TOP_K = 8;
export const MAX_SEMANTIC_QUERY_LENGTH = 1000;

export type RetrievedChunk = {
  document_id: string;
  chunk_index: number;
  page_start: number;
  page_end: number;
  text: string;
  score: number;
};

export type SemanticSearchResponse = {
  document_id: string;
  query: string;
  result_count: number;
  results: RetrievedChunk[];
  status: "completed";
};

type SemanticSearchRequest = {
  query: string;
  top_k?: number;
};

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actualKeys = Object.keys(value);
  return (
    actualKeys.length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 1;
}

function isRetrievedChunk(
  value: unknown,
  documentId: string,
): value is RetrievedChunk {
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
      "score",
    ]) &&
    chunk.document_id === documentId &&
    isPositiveInteger(chunk.chunk_index) &&
    isPositiveInteger(chunk.page_start) &&
    isPositiveInteger(chunk.page_end) &&
    chunk.page_end >= chunk.page_start &&
    typeof chunk.text === "string" &&
    chunk.text.length > 0 &&
    typeof chunk.score === "number" &&
    Number.isFinite(chunk.score) &&
    chunk.score >= -1 &&
    chunk.score <= 1
  );
}

export function isSemanticSearchResponse(
  value: unknown,
): value is SemanticSearchResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const response = value as Record<string, unknown>;
  if (
    !hasExactKeys(response, [
      "document_id",
      "query",
      "result_count",
      "results",
      "status",
    ]) ||
    typeof response.document_id !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      response.document_id,
    ) ||
    typeof response.query !== "string" ||
    response.query.length < 1 ||
    response.query.length > MAX_SEMANTIC_QUERY_LENGTH ||
    typeof response.result_count !== "number" ||
    !Number.isInteger(response.result_count) ||
    response.result_count < 0 ||
    response.result_count > MAX_SEMANTIC_TOP_K ||
    !Array.isArray(response.results) ||
    response.results.length !== response.result_count ||
    response.status !== "completed"
  ) {
    return false;
  }

  const results = response.results as unknown[];
  if (
    !results.every((result) =>
      isRetrievedChunk(result, response.document_id as string),
    )
  ) {
    return false;
  }

  return results.every((result, index) => {
    if (index === 0) {
      return true;
    }
    const previous = results[index - 1] as RetrievedChunk;
    const current = result as RetrievedChunk;
    return (
      previous.score > current.score ||
      (previous.score === current.score &&
        previous.chunk_index < current.chunk_index)
    );
  });
}

export async function searchPdfDocument(
  documentId: string,
  request: SemanticSearchRequest,
  fetchImplementation: typeof fetch = fetch,
): Promise<SemanticSearchResponse> {
  const normalizedQuery = request.query.trim();
  const topK = request.top_k ?? DEFAULT_SEMANTIC_TOP_K;
  if (
    normalizedQuery.length < 1 ||
    normalizedQuery.length > MAX_SEMANTIC_QUERY_LENGTH ||
    !Number.isInteger(topK) ||
    topK < 1 ||
    topK > MAX_SEMANTIC_TOP_K
  ) {
    throw new Error("invalid-document-search-request");
  }

  const response = await fetchImplementation(
    `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/search`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: normalizedQuery, top_k: topK }),
    },
  );

  if (!response.ok) {
    throw new Error("document-search-request-failed");
  }

  const data: unknown = await response.json();
  if (!isSemanticSearchResponse(data)) {
    throw new Error("invalid-document-search-response");
  }
  return data;
}
