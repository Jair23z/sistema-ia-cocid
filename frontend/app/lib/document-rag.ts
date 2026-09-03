import { API_BASE_URL } from "./papers";

export const DEFAULT_DOCUMENT_QUESTION_TOP_K = 4;
export const MAX_DOCUMENT_QUESTION_TOP_K = 8;
export const MAX_DOCUMENT_QUESTION_LENGTH = 1000;
export const INSUFFICIENT_DOCUMENT_EVIDENCE_MESSAGE =
  "No existe evidencia suficiente en los fragmentos recuperados para responder esta pregunta.";

export type EvidenceStatus = "sufficient" | "partial" | "insufficient";

export type DocumentCitation = {
  chunk_index: number;
  page_start: number;
  page_end: number;
};

export type DocumentAnswerResponse = {
  document_id: string;
  query: string;
  answer: string;
  evidence_status: EvidenceStatus;
  citations: DocumentCitation[];
  status: "completed";
};

type DocumentQuestionRequest = {
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

function isDocumentCitation(value: unknown): value is DocumentCitation {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const citation = value as Record<string, unknown>;
  return (
    hasExactKeys(citation, ["chunk_index", "page_start", "page_end"]) &&
    isPositiveInteger(citation.chunk_index) &&
    isPositiveInteger(citation.page_start) &&
    isPositiveInteger(citation.page_end) &&
    citation.page_end >= citation.page_start
  );
}

export function isDocumentAnswerResponse(
  value: unknown,
): value is DocumentAnswerResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const response = value as Record<string, unknown>;
  if (
    !hasExactKeys(response, [
      "document_id",
      "query",
      "answer",
      "evidence_status",
      "citations",
      "status",
    ]) ||
    typeof response.document_id !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      response.document_id,
    ) ||
    typeof response.query !== "string" ||
    response.query.length < 1 ||
    response.query.length > MAX_DOCUMENT_QUESTION_LENGTH ||
    typeof response.answer !== "string" ||
    response.answer.trim().length < 1 ||
    response.answer.length > 6000 ||
    (response.evidence_status !== "sufficient" &&
      response.evidence_status !== "partial" &&
      response.evidence_status !== "insufficient") ||
    !Array.isArray(response.citations) ||
    response.citations.length > MAX_DOCUMENT_QUESTION_TOP_K ||
    response.status !== "completed"
  ) {
    return false;
  }

  if (!response.citations.every(isDocumentCitation)) {
    return false;
  }
  const citations = response.citations as DocumentCitation[];
  const citationKeys = citations.map(
    (citation) =>
      `${citation.chunk_index}:${citation.page_start}:${citation.page_end}`,
  );
  if (new Set(citationKeys).size !== citationKeys.length) {
    return false;
  }

  if (response.evidence_status === "insufficient") {
    return (
      citations.length === 0 &&
      response.answer === INSUFFICIENT_DOCUMENT_EVIDENCE_MESSAGE
    );
  }
  return citations.length > 0;
}

export async function askPdfDocument(
  documentId: string,
  request: DocumentQuestionRequest,
  fetchImplementation: typeof fetch = fetch,
): Promise<DocumentAnswerResponse> {
  const normalizedQuery = request.query.trim();
  const topK = request.top_k ?? DEFAULT_DOCUMENT_QUESTION_TOP_K;
  if (
    normalizedQuery.length < 1 ||
    normalizedQuery.length > MAX_DOCUMENT_QUESTION_LENGTH ||
    !Number.isInteger(topK) ||
    topK < 1 ||
    topK > MAX_DOCUMENT_QUESTION_TOP_K
  ) {
    throw new Error("invalid-document-question-request");
  }

  const response = await fetchImplementation(
    `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/ask`,
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
    throw new Error("document-question-request-failed");
  }

  const data: unknown = await response.json();
  if (!isDocumentAnswerResponse(data)) {
    throw new Error("invalid-document-answer-response");
  }
  return data;
}
