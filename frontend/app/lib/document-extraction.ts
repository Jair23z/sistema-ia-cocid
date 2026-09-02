import { API_BASE_URL } from "./papers";

export const MAX_EXTRACTED_PDF_PAGES = 200;

export type ExtractedPage = {
  page_number: number;
  text: string;
  character_count: number;
  word_count: number;
};

export type ExtractedDocument = {
  document_id: string;
  page_count: number;
  character_count: number;
  word_count: number;
  pages: ExtractedPage[];
  requires_ocr: boolean;
  status: "extracted";
};

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actualKeys = Object.keys(value);
  return (
    actualKeys.length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isExtractedPage(value: unknown, expectedPageNumber: number): value is ExtractedPage {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const page = value as Record<string, unknown>;
  return (
    hasExactKeys(page, [
      "page_number",
      "text",
      "character_count",
      "word_count",
    ]) &&
    page.page_number === expectedPageNumber &&
    typeof page.text === "string" &&
    isNonNegativeInteger(page.character_count) &&
    isNonNegativeInteger(page.word_count)
  );
}

export function isExtractedDocument(value: unknown): value is ExtractedDocument {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const document = value as Record<string, unknown>;
  if (
    !hasExactKeys(document, [
      "document_id",
      "page_count",
      "character_count",
      "word_count",
      "pages",
      "requires_ocr",
      "status",
    ]) ||
    typeof document.document_id !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      document.document_id,
    ) ||
    !isNonNegativeInteger(document.page_count) ||
    document.page_count < 1 ||
    document.page_count > MAX_EXTRACTED_PDF_PAGES ||
    !isNonNegativeInteger(document.character_count) ||
    !isNonNegativeInteger(document.word_count) ||
    !Array.isArray(document.pages) ||
    document.pages.length !== document.page_count ||
    typeof document.requires_ocr !== "boolean" ||
    document.status !== "extracted"
  ) {
    return false;
  }

  if (
    !document.pages.every((page, index) =>
      isExtractedPage(page, index + 1),
    )
  ) {
    return false;
  }

  const pages = document.pages as ExtractedPage[];
  return (
    pages.reduce((total, page) => total + page.character_count, 0) ===
      document.character_count &&
    pages.reduce((total, page) => total + page.word_count, 0) ===
      document.word_count
  );
}

export async function extractPdfDocument(
  documentId: string,
  fetchImplementation: typeof fetch = fetch,
): Promise<ExtractedDocument> {
  const response = await fetchImplementation(
    `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/extract`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    },
  );

  if (!response.ok) {
    throw new Error("document-extraction-request-failed");
  }

  const data: unknown = await response.json();
  if (!isExtractedDocument(data)) {
    throw new Error("invalid-document-extraction-response");
  }

  return data;
}
