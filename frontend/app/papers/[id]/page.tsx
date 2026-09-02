"use client";

import { useRouter } from "next/navigation";
import { use, useEffect, useRef, useState } from "react";

import {
  API_BASE_URL,
  displayAuthors,
  displayValue,
  formatDoi,
  formatPublicationDate,
  formatPublicationType,
  getOpenAccessClassName,
  getOpenAccessLabel,
  getSafeExternalUrl,
  isPaper,
} from "@/app/lib/papers";
import type { Paper } from "@/app/lib/papers";
import { requestScientificAnalysis } from "@/app/lib/scientific-analysis";
import type { ScientificAnalysis } from "@/app/lib/scientific-analysis";

type PaperDetailPageProps = {
  params: Promise<{ id: string }>;
};

export default function PaperDetailPage({ params }: PaperDetailPageProps) {
  const { id } = use(params);
  const router = useRouter();
  const [paper, setPaper] = useState<Paper | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [analysis, setAnalysis] = useState<ScientificAnalysis | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const analysisRequestInProgress = useRef(false);

  useEffect(() => {
    const controller = new AbortController();

    async function loadPaper() {
      setIsLoading(true);
      setError(null);
      setAnalysis(null);
      setAnalysisError(null);

      try {
        const response = await fetch(
          `${API_BASE_URL}/papers/${encodeURIComponent(id)}`,
          {
            headers: { Accept: "application/json" },
            signal: controller.signal,
          },
        );

        if (!response.ok) {
          throw new Error(
            response.status === 404 ? "not-found" : "request-failed",
          );
        }

        const data: unknown = await response.json();

        if (!isPaper(data)) {
          throw new Error("FastAPI devolvió un formato inesperado.");
        }

        setPaper(data);
      } catch (requestError) {
        if (controller.signal.aborted) {
          return;
        }

        console.error(requestError);
        setPaper(null);
        setError(
          requestError instanceof Error && requestError.message === "not-found"
            ? "No se encontró la publicación solicitada."
            : "No fue posible obtener la publicación. Intenta nuevamente en unos momentos.",
        );
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    }

    void loadPaper();
    return () => controller.abort();
  }, [id, reloadKey]);

  const openAccessLabel = paper ? getOpenAccessLabel(paper) : null;
  const doiUrl = paper ? getSafeExternalUrl(paper.doi) : null;
  const openAlexUrl = paper ? getSafeExternalUrl(paper.openalex_url) : null;
  const publicationUrl = paper
    ? getSafeExternalUrl(paper.publication_url)
    : null;

  function returnToResults() {
    const cameFromResults =
      new URLSearchParams(window.location.search).get("from") === "results";

    if (cameFromResults) {
      router.back();
      return;
    }

    router.push("/");
  }

  async function analyzePaper() {
    if (!paper || analysisRequestInProgress.current) {
      return;
    }

    analysisRequestInProgress.current = true;
    setIsAnalyzing(true);
    setAnalysis(null);
    setAnalysisError(null);

    try {
      const data = await requestScientificAnalysis(paper.openalex_id ?? id);
      setAnalysis(data);
    } catch (requestError) {
      console.error(requestError);
      setAnalysisError(
        "No fue posible analizar la publicación. Intenta nuevamente en unos momentos.",
      );
    } finally {
      analysisRequestInProgress.current = false;
      setIsAnalyzing(false);
    }
  }

  return (
    <main className="min-h-screen bg-cocid-white px-4 py-10 text-cocid-navy sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-4xl space-y-6">
        <button
          className="inline-flex items-center rounded-lg px-2 py-1 text-sm font-semibold text-cocid-tech-blue underline decoration-cocid-tech-blue underline-offset-4 hover:text-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue"
          onClick={returnToResults}
          type="button"
        >
          ← Volver a resultados
        </button>

        {isLoading && (
          <p
            aria-live="polite"
            className="rounded-xl border border-cocid-tech-blue bg-cocid-white p-4 text-cocid-navy"
          >
            Cargando publicación...
          </p>
        )}

        {!isLoading && error && (
          <div
            className="space-y-3 rounded-xl border border-cocid-gold bg-cocid-white p-5 text-cocid-graphite"
            role="alert"
          >
            <p>{error}</p>
            <button
              className="rounded-lg bg-cocid-tech-blue px-4 py-2 text-sm font-semibold text-cocid-white hover:bg-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue"
              onClick={() => setReloadKey((currentKey) => currentKey + 1)}
              type="button"
            >
              Reintentar
            </button>
          </div>
        )}

        {!isLoading && !error && paper && (
          <article className="space-y-8 rounded-2xl border border-cocid-graphite bg-cocid-white p-6 sm:p-8">
            <header className="space-y-4">
              <div className="flex flex-col items-start gap-3 sm:flex-row sm:justify-between">
                <div className="space-y-2">
                  <p className="border-l-4 border-cocid-gold pl-3 text-sm font-semibold uppercase tracking-[0.16em] text-cocid-navy">
                    Detalle de publicación
                  </p>
                  <h1 className="break-words text-3xl font-bold leading-tight sm:text-4xl">
                    {displayValue(paper.title, "Título no disponible")}
                  </h1>
                </div>
                {openAccessLabel && (
                  <span
                    className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${getOpenAccessClassName(paper)}`}
                  >
                    {openAccessLabel}
                  </span>
                )}
              </div>
              <p className="break-words leading-7 text-cocid-graphite">
                {displayAuthors(paper.authors)}
              </p>
            </header>

            <dl className="grid gap-5 border-y border-cocid-graphite py-6 text-sm sm:grid-cols-2">
              <div>
                <dt className="font-semibold text-cocid-navy">Año</dt>
                <dd className="mt-1 text-cocid-graphite">
                  {paper.year ?? "Año no disponible"}
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-cocid-navy">
                  Fecha de publicación
                </dt>
                <dd className="mt-1 text-cocid-graphite">
                  {formatPublicationDate(paper.publication_date)}
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-cocid-navy">
                  Revista o fuente
                </dt>
                <dd className="mt-1 text-cocid-graphite">
                  {displayValue(paper.source, "Fuente no disponible")}
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-cocid-navy">
                  Tipo de publicación
                </dt>
                <dd className="mt-1 text-cocid-graphite">
                  {formatPublicationType(paper.publication_type)}
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-cocid-navy">Citas</dt>
                <dd className="mt-1 text-cocid-graphite">
                  {paper.citations ?? "Citas no disponibles"}
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-cocid-navy">OpenAlex ID</dt>
                <dd className="mt-1 break-all text-cocid-graphite">
                  {displayValue(
                    paper.openalex_id,
                    "OpenAlex ID no disponible",
                  )}
                </dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="font-semibold text-cocid-navy">DOI</dt>
                <dd className="mt-1 break-all text-cocid-graphite">
                  {paper.doi && doiUrl ? (
                    <a
                      className="text-cocid-tech-blue underline decoration-cocid-tech-blue underline-offset-4 hover:text-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue"
                      href={doiUrl}
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      {formatDoi(paper.doi)}
                    </a>
                  ) : paper.doi ? (
                    formatDoi(paper.doi)
                  ) : (
                    "DOI no disponible"
                  )}
                </dd>
              </div>
            </dl>

            <section className="space-y-3">
              <h2 className="text-xl font-semibold">Abstract</h2>
              <p className="max-w-prose whitespace-pre-line break-words leading-8 text-cocid-graphite">
                {displayValue(
                  paper.abstract,
                  "El abstract no está disponible en OpenAlex.",
                )}
              </p>
            </section>

            <section
              aria-busy={isAnalyzing}
              className="space-y-4 border-t border-cocid-graphite pt-6"
            >
              <div className="space-y-2">
                <h2 className="text-xl font-semibold text-cocid-navy">
                  Análisis mediante inteligencia artificial
                </h2>
                <p className="text-sm leading-6 text-cocid-graphite">
                  Genera un análisis estructurado utilizando únicamente la
                  información disponible de esta publicación.
                </p>
              </div>

              <button
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-cocid-tech-blue px-4 py-2 text-sm font-semibold text-cocid-white hover:bg-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue disabled:cursor-not-allowed disabled:bg-cocid-graphite sm:w-auto"
                disabled={isAnalyzing}
                onClick={analyzePaper}
                type="button"
              >
                {isAnalyzing && (
                  <span
                    aria-hidden="true"
                    className="h-4 w-4 animate-spin rounded-full border-2 border-cocid-white border-t-cocid-turquoise"
                  />
                )}
                {isAnalyzing ? "Analizando..." : "Analizar con IA"}
              </button>

              {isAnalyzing && (
                <div
                  className="flex items-center gap-3 rounded-xl border border-cocid-tech-blue bg-cocid-white p-4 text-cocid-navy"
                  role="status"
                >
                  <span
                    aria-hidden="true"
                    className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-cocid-graphite border-t-cocid-turquoise"
                  />
                  <p>Analizando publicación...</p>
                </div>
              )}

              {!isAnalyzing && analysisError && (
                <div
                  className="rounded-xl border border-cocid-gold bg-cocid-white p-4 text-cocid-graphite"
                  role="alert"
                >
                  <p>{analysisError}</p>
                  <p className="mt-1 text-sm">
                    Puedes volver a intentarlo con el botón de análisis.
                  </p>
                </div>
              )}

              {!isAnalyzing && analysis && (
                <div
                  className="space-y-6 rounded-xl border border-cocid-turquoise bg-cocid-white p-5 sm:p-6"
                  aria-live="polite"
                >
                  <dl className="space-y-5">
                    <div>
                      <dt className="font-semibold text-cocid-navy">
                        Objetivo
                      </dt>
                      <dd className="mt-1 whitespace-pre-line break-words leading-7 text-cocid-graphite">
                        {analysis.objective}
                      </dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-cocid-navy">
                        Metodología
                      </dt>
                      <dd className="mt-1 whitespace-pre-line break-words leading-7 text-cocid-graphite">
                        {analysis.methodology}
                      </dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-cocid-navy">
                        Resultados
                      </dt>
                      <dd className="mt-1 whitespace-pre-line break-words leading-7 text-cocid-graphite">
                        {analysis.results}
                      </dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-cocid-navy">
                        Conclusiones
                      </dt>
                      <dd className="mt-1 whitespace-pre-line break-words leading-7 text-cocid-graphite">
                        {analysis.conclusions}
                      </dd>
                    </div>
                  </dl>

                  <div className="space-y-2">
                    <h3 className="font-semibold text-cocid-navy">
                      Hallazgos principales
                    </h3>
                    {analysis.findings.length > 0 ? (
                      <ul className="list-disc space-y-2 pl-5 text-cocid-graphite marker:text-cocid-turquoise">
                        {analysis.findings.map((finding, index) => (
                          <li className="break-words leading-7" key={index}>
                            {finding}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-cocid-graphite">
                        No se identificaron hallazgos con la información
                        disponible.
                      </p>
                    )}
                  </div>
                </div>
              )}
            </section>

            <section className="space-y-3">
              <h2 className="text-xl font-semibold">Enlaces</h2>
              <div className="flex flex-wrap gap-3">
                {openAlexUrl && (
                  <a
                    className="inline-flex w-full justify-center rounded-lg bg-cocid-tech-blue px-4 py-2 text-sm font-semibold text-cocid-white hover:bg-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue sm:w-auto"
                    href={openAlexUrl}
                    rel="noopener noreferrer"
                    target="_blank"
                  >
                    Ver en OpenAlex
                  </a>
                )}
                {publicationUrl && (
                  <a
                    className="inline-flex w-full justify-center rounded-lg border border-cocid-tech-blue bg-cocid-white px-4 py-2 text-sm font-semibold text-cocid-tech-blue hover:bg-cocid-tech-blue hover:text-cocid-white focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue sm:w-auto"
                    href={publicationUrl}
                    rel="noopener noreferrer"
                    target="_blank"
                  >
                    Abrir publicación
                  </a>
                )}
                {!openAlexUrl && !publicationUrl && (
                  <p className="text-sm text-cocid-graphite">
                    No hay enlaces disponibles para esta publicación.
                  </p>
                )}
              </div>
            </section>
          </article>
        )}
      </div>
    </main>
  );
}
