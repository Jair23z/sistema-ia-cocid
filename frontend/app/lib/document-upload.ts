import { API_BASE_URL } from "./papers";

export const MAX_PDF_UPLOAD_BYTES = 15 * 1024 * 1024;
export const PDF_MIME_TYPE = "application/pdf";

export type DocumentUploadResponse = {
  document_id: string;
  filename: string;
  size_bytes: number;
  status: "uploaded";
};

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actualKeys = Object.keys(value);
  return (
    actualKeys.length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

export function getPdfSelectionError(file: File): string | null {
  if (!file.name.toLocaleLowerCase("en-US").endsWith(".pdf")) {
    return "Selecciona un archivo con extensión .pdf.";
  }

  if (file.type.toLocaleLowerCase("en-US") !== PDF_MIME_TYPE) {
    return "El archivo seleccionado debe tener el tipo application/pdf.";
  }

  if (file.size === 0) {
    return "El archivo PDF está vacío.";
  }

  if (file.size > MAX_PDF_UPLOAD_BYTES) {
    return "El archivo PDF supera el límite permitido de 15 MiB.";
  }

  return null;
}

export function formatFileSize(sizeBytes: number): string {
  if (sizeBytes < 1024) {
    return `${sizeBytes} ${sizeBytes === 1 ? "byte" : "bytes"}`;
  }

  const kibibytes = sizeBytes / 1024;
  if (kibibytes < 1024) {
    return `${kibibytes.toFixed(1)} KiB`;
  }

  return `${(kibibytes / 1024).toFixed(1)} MiB`;
}

export function isDocumentUploadResponse(
  value: unknown,
): value is DocumentUploadResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const response = value as Record<string, unknown>;
  return (
    hasExactKeys(response, [
      "document_id",
      "filename",
      "size_bytes",
      "status",
    ]) &&
    typeof response.document_id === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      response.document_id,
    ) &&
    typeof response.filename === "string" &&
    response.filename.trim().length > 0 &&
    Number.isInteger(response.size_bytes) &&
    Number(response.size_bytes) > 0 &&
    Number(response.size_bytes) <= MAX_PDF_UPLOAD_BYTES &&
    response.status === "uploaded"
  );
}

export async function uploadPdfDocument(
  file: File,
  fetchImplementation: typeof fetch = fetch,
): Promise<DocumentUploadResponse> {
  if (getPdfSelectionError(file)) {
    throw new Error("invalid-pdf-selection");
  }

  const body = new FormData();
  body.append("file", file, file.name);

  const response = await fetchImplementation(
    `${API_BASE_URL}/documents/upload`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
      body,
    },
  );

  if (!response.ok) {
    throw new Error("document-upload-request-failed");
  }

  const data: unknown = await response.json();
  if (!isDocumentUploadResponse(data)) {
    throw new Error("invalid-document-upload-response");
  }

  return data;
}
