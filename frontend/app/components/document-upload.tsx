"use client";

import { useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import {
  preparePdfDocument,
  type ChunkedDocument,
} from "@/app/lib/document-chunking";
import {
  askPdfDocument,
  type DocumentAnswerResponse,
} from "@/app/lib/document-rag";
import {
  searchPdfDocument,
  type SemanticSearchResponse,
} from "@/app/lib/document-search";
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
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] =
    useState<SemanticSearchResponse | null>(null);
  const [isSearchingDocument, setIsSearchingDocument] = useState(false);
  const [questionQuery, setQuestionQuery] = useState("");
  const [answerResult, setAnswerResult] =
    useState<DocumentAnswerResponse | null>(null);
  const [isAskingDocument, setIsAskingDocument] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extractionError, setExtractionError] = useState<string | null>(null);
  const [chunkingError, setChunkingError] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [questionError, setQuestionError] = useState<string | null>(null);
  const uploadInProgress = useRef(false);
  const extractionInProgress = useRef(false);
  const chunkingInProgress = useRef(false);
  const searchInProgress = useRef(false);
  const questionInProgress = useRef(false);

  function resetDocumentSearch() {
    setSearchQuery("");
    setSearchResult(null);
    setSearchError(null);
  }

  function resetDocumentQuestion() {
    setQuestionQuery("");
    setAnswerResult(null);
    setQuestionError(null);
  }

  function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setUploadResult(null);
    setExtractionResult(null);
    setExtractionError(null);
    setChunkingResult(null);
    setChunkingError(null);
    resetDocumentSearch();
    resetDocumentQuestion();

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
    resetDocumentSearch();
    resetDocumentQuestion();

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
    resetDocumentSearch();
    resetDocumentQuestion();

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
    resetDocumentSearch();
    resetDocumentQuestion();

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

  async function handleDocumentSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuery = searchQuery.trim();
    if (
      searchInProgress.current ||
      questionInProgress.current ||
      chunkingResult?.status !== "chunked" ||
      !normalizedQuery
    ) {
      return;
    }

    searchInProgress.current = true;
    setIsSearchingDocument(true);
    setSearchError(null);
    setSearchResult(null);

    try {
      const response = await searchPdfDocument(chunkingResult.document_id, {
        query: normalizedQuery,
      });
      setSearchResult(response);
    } catch (searchRequestError) {
      console.error(searchRequestError);
      setSearchError(
        "No fue posible buscar dentro del documento. Intenta nuevamente.",
      );
    } finally {
      searchInProgress.current = false;
      setIsSearchingDocument(false);
    }
  }

  async function handleDocumentQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuery = questionQuery.trim();
    if (
      questionInProgress.current ||
      searchInProgress.current ||
      chunkingResult?.status !== "chunked" ||
      !normalizedQuery
    ) {
      return;
    }

    questionInProgress.current = true;
    setIsAskingDocument(true);
    setQuestionError(null);
    setAnswerResult(null);

    try {
      const response = await askPdfDocument(chunkingResult.document_id, {
        query: normalizedQuery,
      });
      setAnswerResult(response);
    } catch (questionRequestError) {
      console.error(questionRequestError);
      setQuestionError(
        "No fue posible responder la pregunta sobre el documento. Intenta nuevamente.",
      );
    } finally {
      questionInProgress.current = false;
      setIsAskingDocument(false);
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
            disabled={
              isUploading ||
              isExtracting ||
              isChunking ||
              isSearchingDocument ||
              isAskingDocument
            }
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
            isChunking ||
            isSearchingDocument ||
            isAskingDocument
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
            disabled={
              isExtracting ||
              isChunking ||
              isSearchingDocument ||
              isAskingDocument
            }
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
              disabled={
                isChunking || isSearchingDocument || isAskingDocument
              }
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

      {chunkingResult?.status === "chunked" && (
        <section
          aria-labelledby="document-search-title"
          className="mt-4 rounded-xl border border-cocid-gold bg-cocid-white p-4"
        >
          <h3
            className="text-sm font-semibold uppercase tracking-wide text-cocid-navy"
            id="document-search-title"
          >
            Buscar dentro del documento
          </h3>
          <p className="mt-1 text-sm text-cocid-graphite">
            Recupera los fragmentos del PDF más relacionados con tu consulta.
          </p>
          <form
            aria-busy={isSearchingDocument}
            aria-label="Búsqueda dentro del documento"
            className="mt-4 flex flex-col gap-3 sm:flex-row"
            onSubmit={handleDocumentSearch}
          >
            <label className="min-w-0 flex-1">
              <span className="sr-only">Consulta dentro del documento</span>
              <input
                className="w-full rounded-xl border border-cocid-graphite bg-cocid-white px-4 py-3 text-cocid-navy outline-none placeholder:text-cocid-graphite focus:border-cocid-tech-blue focus:ring-4 focus:ring-cocid-tech-blue disabled:cursor-not-allowed"
                disabled={isSearchingDocument || isAskingDocument}
                maxLength={1000}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="¿Qué metodología utilizó el estudio?"
                type="search"
                value={searchQuery}
              />
            </label>
            <button
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-cocid-tech-blue px-5 py-2 font-semibold text-cocid-white transition hover:bg-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue disabled:cursor-not-allowed disabled:bg-cocid-graphite"
              disabled={
                isSearchingDocument ||
                isAskingDocument ||
                searchQuery.trim().length === 0
              }
              type="submit"
            >
              {isSearchingDocument && (
                <span
                  aria-hidden="true"
                  className="h-4 w-4 animate-spin rounded-full border-2 border-cocid-white border-t-cocid-navy"
                />
              )}
              {isSearchingDocument
                ? "Buscando en documento..."
                : "Buscar en documento"}
            </button>
          </form>

          {isSearchingDocument && (
            <p className="mt-4 text-sm text-cocid-graphite" role="status">
              Buscando fragmentos relevantes...
            </p>
          )}

          {searchError && (
            <p
              className="mt-4 rounded-xl border border-cocid-gold bg-cocid-white p-4 text-sm text-cocid-graphite"
              role="alert"
            >
              {searchError}
            </p>
          )}

          {searchResult && (
            <div className="mt-5">
              <p className="font-semibold text-cocid-navy">
                {searchResult.result_count}{" "}
                {searchResult.result_count === 1
                  ? "fragmento recuperado"
                  : "fragmentos recuperados"}
              </p>
              <ol className="mt-3 space-y-3">
                {searchResult.results.map((result) => {
                  const pageLabel =
                    result.page_start === result.page_end
                      ? `Página ${result.page_start}`
                      : `Páginas ${result.page_start}–${result.page_end}`;
                  const preview =
                    result.text.length > 360
                      ? `${result.text.slice(0, 360).trimEnd()}…`
                      : result.text;
                  return (
                    <li
                      className="rounded-xl border border-cocid-turquoise bg-cocid-white p-4"
                      key={result.chunk_index}
                    >
                      <div className="flex flex-col gap-1 text-sm sm:flex-row sm:items-center sm:justify-between">
                        <span className="font-semibold text-cocid-navy">
                          {pageLabel}
                        </span>
                        <span className="text-cocid-graphite">
                          Relevancia: {result.score.toFixed(3)}
                        </span>
                      </div>
                      <p className="mt-2 break-words text-sm leading-6 text-cocid-graphite">
                        {preview}
                      </p>
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
        </section>
      )}

      {chunkingResult?.status === "chunked" && (
        <section
          aria-labelledby="document-question-title"
          className="mt-4 rounded-xl border border-cocid-turquoise bg-cocid-white p-4"
        >
          <h3
            className="text-sm font-semibold uppercase tracking-wide text-cocid-navy"
            id="document-question-title"
          >
            Preguntar sobre el documento
          </h3>
          <p className="mt-1 text-sm text-cocid-graphite">
            Genera una respuesta basada exclusivamente en los fragmentos
            recuperados del PDF.
          </p>
          <form
            aria-busy={isAskingDocument}
            aria-label="Pregunta sobre el documento"
            className="mt-4 flex flex-col gap-3 sm:flex-row"
            onSubmit={handleDocumentQuestion}
          >
            <label className="min-w-0 flex-1" htmlFor="document-question">
              <span className="sr-only">Pregunta sobre el documento</span>
              <input
                className="w-full rounded-xl border border-cocid-graphite bg-cocid-white px-4 py-3 text-cocid-navy outline-none placeholder:text-cocid-graphite focus:border-cocid-tech-blue focus:ring-4 focus:ring-cocid-tech-blue disabled:cursor-not-allowed"
                disabled={isAskingDocument || isSearchingDocument}
                id="document-question"
                maxLength={1000}
                onChange={(event) => setQuestionQuery(event.target.value)}
                placeholder="Escribe una pregunta sobre el documento"
                type="search"
                value={questionQuery}
              />
            </label>
            <button
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-cocid-tech-blue px-5 py-2 font-semibold text-cocid-white transition hover:bg-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue disabled:cursor-not-allowed disabled:bg-cocid-graphite"
              disabled={
                isAskingDocument ||
                isSearchingDocument ||
                questionQuery.trim().length === 0
              }
              type="submit"
            >
              {isAskingDocument && (
                <span
                  aria-hidden="true"
                  className="h-4 w-4 animate-spin rounded-full border-2 border-cocid-white border-t-cocid-navy"
                />
              )}
              {isAskingDocument
                ? "Consultando documento..."
                : "Preguntar al documento"}
            </button>
          </form>

          {isAskingDocument && (
            <p className="mt-4 text-sm text-cocid-graphite" role="status">
              Consultando documento...
            </p>
          )}

          {questionError && (
            <p
              className="mt-4 rounded-xl border border-cocid-gold bg-cocid-white p-4 text-sm text-cocid-graphite"
              role="alert"
            >
              {questionError}
            </p>
          )}

          {answerResult && (
            <div className="mt-5 rounded-xl border border-cocid-gold bg-cocid-white p-4">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <h4 className="font-semibold text-cocid-navy">
                  Respuesta de IA
                </h4>
                <span
                  className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold ${
                    answerResult.evidence_status === "sufficient"
                      ? "border-cocid-turquoise text-cocid-turquoise"
                      : answerResult.evidence_status === "partial"
                        ? "border-cocid-gold text-cocid-graphite"
                        : "border-cocid-graphite text-cocid-graphite"
                  }`}
                >
                  {answerResult.evidence_status === "sufficient"
                    ? "Evidencia suficiente"
                    : answerResult.evidence_status === "partial"
                      ? "Evidencia parcial"
                      : "Evidencia insuficiente"}
                </span>
              </div>
              <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-cocid-graphite">
                {answerResult.answer}
              </p>

              {answerResult.citations.length > 0 && (
                <div className="mt-4 border-t border-cocid-gold pt-3">
                  <p className="text-sm font-semibold text-cocid-navy">
                    Fuentes
                  </p>
                  <ul className="mt-2 flex flex-wrap gap-2">
                    {Array.from(
                      new Map(
                        answerResult.citations.map((citation) => [
                          `${citation.page_start}:${citation.page_end}`,
                          citation,
                        ]),
                      ).values(),
                    ).map((citation) => (
                      <li
                        className="rounded-full border border-cocid-turquoise bg-cocid-white px-3 py-1 text-xs font-semibold text-cocid-graphite"
                        key={`${citation.page_start}:${citation.page_end}`}
                      >
                        {citation.page_start === citation.page_end
                          ? `Página ${citation.page_start}`
                          : `Páginas ${citation.page_start}–${citation.page_end}`}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      )}
    </section>
  );
}
