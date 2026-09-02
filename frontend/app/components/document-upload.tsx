"use client";

import { useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import {
  preparePdfDocument,
  type ChunkedDocument,
} from "@/app/lib/document-chunking";
import {
  extractPdfDocument,
  type ExtractedDocument,
} from "@/app/lib/document-extraction";
import {
  formatFileSize,
  getPdfSelectionError,
  uploadPdfDocument,
  type DocumentUploadResponse,
} from "@/app/lib/document-upload";

export function DocumentUpload() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] =
    useState<DocumentUploadResponse | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [extractionResult, setExtractionResult] =
    useState<ExtractedDocument | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [chunkingResult, setChunkingResult] =
    useState<ChunkedDocument | null>(null);
  const [isChunking, setIsChunking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extractionError, setExtractionError] = useState<string | null>(null);
  const [chunkingError, setChunkingError] = useState<string | null>(null);
  const uploadInProgress = useRef(false);
  const extractionInProgress = useRef(false);
  const chunkingInProgress = useRef(false);

  function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setUploadResult(null);
    setExtractionResult(null);
    setExtractionError(null);
    setChunkingResult(null);
    setChunkingError(null);

    if (!file) {
      setError(null);
      return;
    }

    setError(getPdfSelectionError(file));
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (uploadInProgress.current || !selectedFile) {
      return;
    }

    const selectionError = getPdfSelectionError(selectedFile);
    if (selectionError) {
      setError(selectionError);
      return;
    }

    uploadInProgress.current = true;
    setIsUploading(true);
    setError(null);
    setUploadResult(null);
    setExtractionResult(null);
    setExtractionError(null);
    setChunkingResult(null);
    setChunkingError(null);

    try {
      const response = await uploadPdfDocument(selectedFile);
      setUploadResult(response);
    } catch (uploadError) {
      console.error(uploadError);
      setError(
        "No fue posible subir el documento. Verifica el archivo e intenta nuevamente.",
      );
    } finally {
      uploadInProgress.current = false;
      setIsUploading(false);
    }
  }

  async function handleExtraction() {
    if (extractionInProgress.current || !uploadResult) {
      return;
    }

    extractionInProgress.current = true;
    setIsExtracting(true);
    setExtractionError(null);
    setExtractionResult(null);
    setChunkingResult(null);
    setChunkingError(null);

    try {
      const response = await extractPdfDocument(uploadResult.document_id);
      setExtractionResult(response);
    } catch (extractionRequestError) {
      console.error(extractionRequestError);
      setExtractionError(
        "No fue posible procesar el documento. Verifica el PDF e intenta nuevamente.",
      );
    } finally {
      extractionInProgress.current = false;
      setIsExtracting(false);
    }
  }

  async function handleChunking() {
    if (chunkingInProgress.current || !extractionResult) {
      return;
    }

    chunkingInProgress.current = true;
    setIsChunking(true);
    setChunkingError(null);
    setChunkingResult(null);

    try {
      const response = await preparePdfDocument(
        extractionResult.document_id,
      );
      setChunkingResult(response);
    } catch (chunkingRequestError) {
      console.error(chunkingRequestError);
      setChunkingError(
        "No fue posible preparar el documento. Intenta nuevamente.",
      );
    } finally {
      chunkingInProgress.current = false;
      setIsChunking(false);
    }
  }

  const selectionError = selectedFile
    ? getPdfSelectionError(selectedFile)
    : null;

  return (
    <section
      aria-labelledby="document-upload-title"
      className="rounded-2xl border border-cocid-gold bg-cocid-white p-5"
    >
      <div className="space-y-1">
        <h2
          className="text-xl font-semibold text-cocid-navy"
          id="document-upload-title"
        >
          Analizar documento propio
        </h2>
        <p className="text-sm text-cocid-graphite">
          Selecciona un artículo científico en PDF. En este paso únicamente se
          cargará el archivo; todavía no se analizará su contenido.
        </p>
      </div>

      <form className="mt-4 space-y-4" onSubmit={handleUpload}>
        <div>
          <label
            className="block text-sm font-semibold text-cocid-navy"
            htmlFor="scientific-pdf"
          >
            Documento PDF
          </label>
          <input
            accept=".pdf,application/pdf"
            className="mt-2 block w-full rounded-lg border border-cocid-graphite bg-cocid-white px-3 py-2 text-sm text-cocid-graphite file:mr-3 file:rounded-lg file:border-0 file:bg-cocid-tech-blue file:px-3 file:py-2 file:font-semibold file:text-cocid-white focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue disabled:cursor-not-allowed"
            disabled={isUploading || isExtracting || isChunking}
            id="scientific-pdf"
            name="scientific-pdf"
            onChange={handleFileSelection}
            type="file"
          />
        </div>

        {selectedFile && (
          <dl className="grid gap-2 rounded-xl border border-cocid-turquoise bg-cocid-white p-3 text-sm sm:grid-cols-2">
            <div className="min-w-0">
              <dt className="font-semibold text-cocid-navy">Archivo</dt>
              <dd className="break-words text-cocid-graphite">
                {selectedFile.name}
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-cocid-navy">Tamaño</dt>
              <dd className="text-cocid-graphite">
                {formatFileSize(selectedFile.size)}
              </dd>
            </div>
          </dl>
        )}

        <button
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-cocid-tech-blue px-5 py-2 font-semibold text-cocid-white transition hover:bg-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue disabled:cursor-not-allowed disabled:bg-cocid-graphite"
          disabled={
            !selectedFile ||
            selectionError !== null ||
            isUploading ||
            isExtracting ||
            isChunking
          }
          type="submit"
        >
          {isUploading && (
            <span
              aria-hidden="true"
              className="h-4 w-4 animate-spin rounded-full border-2 border-cocid-white border-t-cocid-navy"
            />
          )}
          {isUploading ? "Subiendo documento..." : "Subir documento"}
        </button>
      </form>

      {error && (
        <p
          className="mt-4 rounded-xl border border-cocid-gold bg-cocid-white p-4 text-sm text-cocid-graphite"
          role="alert"
        >
          {error}
        </p>
      )}

      {uploadResult && (
        <div
          className="mt-4 rounded-xl border border-cocid-turquoise bg-cocid-white p-4"
          role="status"
        >
          <p className="font-semibold text-cocid-navy">
            Documento cargado correctamente
          </p>
          <p className="mt-1 break-words text-sm text-cocid-graphite">
            {uploadResult.filename} · {formatFileSize(uploadResult.size_bytes)}
          </p>
          <button
            className="mt-4 inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-cocid-tech-blue px-5 py-2 font-semibold text-cocid-white transition hover:bg-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue disabled:cursor-not-allowed disabled:bg-cocid-graphite"
            disabled={isExtracting || isChunking}
            onClick={handleExtraction}
            type="button"
          >
            {isExtracting && (
              <span
                aria-hidden="true"
                className="h-4 w-4 animate-spin rounded-full border-2 border-cocid-white border-t-cocid-navy"
              />
            )}
            {isExtracting ? "Procesando documento..." : "Procesar documento"}
          </button>
        </div>
      )}

      {extractionError && (
        <p
          className="mt-4 rounded-xl border border-cocid-gold bg-cocid-white p-4 text-sm text-cocid-graphite"
          role="alert"
        >
          {extractionError}
        </p>
      )}

      {extractionResult && (
        <div className="mt-4 space-y-4" role="status">
          <div className="rounded-xl border border-cocid-turquoise bg-cocid-white p-4">
            <p className="font-semibold text-cocid-navy">
              Documento procesado correctamente
            </p>
            <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <dt className="font-semibold text-cocid-navy">Páginas</dt>
                <dd className="text-cocid-graphite">
                  {extractionResult.page_count}
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-cocid-navy">Palabras</dt>
                <dd className="text-cocid-graphite">
                  {extractionResult.word_count}
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-cocid-navy">Caracteres</dt>
                <dd className="text-cocid-graphite">
                  {extractionResult.character_count}
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-cocid-navy">Estado</dt>
                <dd className="text-cocid-graphite">Extraído</dd>
              </div>
            </dl>
            <button
              className="mt-4 inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-cocid-tech-blue px-5 py-2 font-semibold text-cocid-white transition hover:bg-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue disabled:cursor-not-allowed disabled:bg-cocid-graphite"
              disabled={isChunking}
              onClick={handleChunking}
              type="button"
            >
              {isChunking && (
                <span
                  aria-hidden="true"
                  className="h-4 w-4 animate-spin rounded-full border-2 border-cocid-white border-t-cocid-navy"
                />
              )}
              {isChunking ? "Preparando documento..." : "Preparar documento"}
            </button>
          </div>

          {extractionResult.requires_ocr && (
            <p className="rounded-xl border border-cocid-gold bg-cocid-white p-4 text-sm text-cocid-graphite">
              El documento tiene poco texto extraíble y probablemente requiere
              reconocimiento óptico de caracteres (OCR). En este paso no se
              ejecutó OCR.
            </p>
          )}
        </div>
      )}

      {chunkingError && (
        <p
          className="mt-4 rounded-xl border border-cocid-gold bg-cocid-white p-4 text-sm text-cocid-graphite"
          role="alert"
        >
          {chunkingError}
        </p>
      )}

      {chunkingResult && (
        <div
          className="mt-4 rounded-xl border border-cocid-turquoise bg-cocid-white p-4"
          role="status"
        >
          {chunkingResult.status === "chunked" ? (
            <p className="font-semibold text-cocid-navy">
              Documento preparado correctamente
            </p>
          ) : (
            <p className="font-semibold text-cocid-navy">
              No existe suficiente texto extraído para preparar el documento.
            </p>
          )}
          <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="font-semibold text-cocid-navy">Fragmentos</dt>
              <dd className="text-cocid-graphite">
                {chunkingResult.chunk_count}
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-cocid-navy">Total de palabras</dt>
              <dd className="text-cocid-graphite">
                {chunkingResult.total_word_count}
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-cocid-navy">
                Promedio por fragmento
              </dt>
              <dd className="text-cocid-graphite">
                {chunkingResult.chunk_count === 0
                  ? 0
                  : Math.round(
                      chunkingResult.chunks.reduce(
                        (total, chunk) => total + chunk.word_count,
                        0,
                      ) / chunkingResult.chunk_count,
                    )}{" "}
                palabras
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-cocid-navy">Estado</dt>
              <dd className="text-cocid-graphite">
                {chunkingResult.status === "chunked"
                  ? "Preparado"
                  : "Texto insuficiente"}
              </dd>
            </div>
          </dl>
        </div>
      )}
    </section>
  );
}
