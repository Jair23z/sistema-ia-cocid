"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import {
  API_BASE_URL,
  PAPER_SEARCH_STORAGE_KEY,
  PUBLICATION_TYPE_OPTIONS,
  displayAuthors,
  displayValue,
  formatDoi,
  getOpenAccessClassName,
  getOpenAccessLabel,
  getSafeExternalUrl,
  isPaper,
} from "@/app/lib/papers";
import type {
  OpenAccessFilter,
  Paper,
  PublicationTypeFilter,
} from "@/app/lib/papers";

export default function Home() {
  const [query, setQuery] = useState("");
  const [papers, setPapers] = useState<Paper[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fromYear, setFromYear] = useState("");
  const [toYear, setToYear] = useState("");
  const [publicationType, setPublicationType] =
    useState<PublicationTypeFilter>("");
  const [openAccess, setOpenAccess] = useState<OpenAccessFilter>("");
  const requestInProgress = useRef(false);

  useEffect(() => {
    try {
      const savedSearch = sessionStorage.getItem(PAPER_SEARCH_STORAGE_KEY);

      if (!savedSearch) {
        return;
      }

      const parsedSearch: unknown = JSON.parse(savedSearch);

      if (typeof parsedSearch !== "object" || parsedSearch === null) {
        throw new Error("La búsqueda guardada no es válida.");
      }

      const saved = parsedSearch as Record<string, unknown>;
      const savedPublicationType = saved.publicationType;
      const savedOpenAccess = saved.openAccess;
      const validPublicationType =
        savedPublicationType === "" ||
        (typeof savedPublicationType === "string" &&
          PUBLICATION_TYPE_OPTIONS.some(
            (option) => option.value === savedPublicationType,
          ));
      const validOpenAccess =
        savedOpenAccess === "" ||
        savedOpenAccess === "true" ||
        savedOpenAccess === "false";

      if (
        typeof saved.query !== "string" ||
        typeof saved.fromYear !== "string" ||
        typeof saved.toYear !== "string" ||
        !validPublicationType ||
        !validOpenAccess ||
        !Array.isArray(saved.papers) ||
        !saved.papers.every(isPaper)
      ) {
        throw new Error("La búsqueda guardada está incompleta.");
      }

      const restoreTimeout = window.setTimeout(() => {
        setQuery(saved.query as string);
        setFromYear(saved.fromYear as string);
        setToYear(saved.toYear as string);
        setPublicationType(savedPublicationType as PublicationTypeFilter);
        setOpenAccess(savedOpenAccess as OpenAccessFilter);
        setPapers(saved.papers as Paper[]);
        setHasSearched(true);
      }, 0);

      return () => window.clearTimeout(restoreTimeout);
    } catch (restoreError) {
      console.warn(restoreError);
      sessionStorage.removeItem(PAPER_SEARCH_STORAGE_KEY);
    }
  }, []);

  const activeFilters = [
    fromYear ? `Desde ${fromYear}` : null,
    toYear ? `Hasta ${toYear}` : null,
    publicationType
      ? PUBLICATION_TYPE_OPTIONS.find(
          (option) => option.value === publicationType,
        )?.label ?? publicationType
      : null,
    openAccess === "true"
      ? "Acceso abierto"
      : openAccess === "false"
        ? "Acceso cerrado"
        : null,
  ].filter((filter): filter is string => filter !== null);
  const hasActiveFilters = activeFilters.length > 0;

  function clearFilters() {
    setFromYear("");
    setToYear("");
    setPublicationType("");
    setOpenAccess("");
  }

  function preserveSearchForDetails() {
    try {
      sessionStorage.setItem(
        PAPER_SEARCH_STORAGE_KEY,
        JSON.stringify({
          query,
          fromYear,
          toYear,
          publicationType,
          openAccess,
          papers,
        }),
      );
    } catch (storageError) {
      console.warn(storageError);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (requestInProgress.current) {
      return;
    }

    const normalizedQuery = query.trim();

    if (!normalizedQuery) {
      setError("Escribe un tema antes de buscar.");
      setPapers([]);
      setHasSearched(false);
      return;
    }

    if (fromYear && toYear && Number(fromYear) > Number(toYear)) {
      setError("El año inicial no puede ser mayor que el año final.");
      setPapers([]);
      setHasSearched(false);
      return;
    }

    requestInProgress.current = true;
    setIsLoading(true);
    setError(null);
    setPapers([]);
    setHasSearched(true);

    const params = new URLSearchParams({
      query: normalizedQuery,
      limit: "10",
    });

    if (fromYear) {
      params.set("from_year", fromYear);
    }

    if (toYear) {
      params.set("to_year", toYear);
    }

    if (publicationType) {
      params.set("publication_type", publicationType);
    }

    if (openAccess) {
      params.set("is_open_access", openAccess);
    }

    try {
      const response = await fetch(`${API_BASE_URL}/papers?${params}`, {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`La búsqueda respondió con estado ${response.status}.`);
      }

      const data: unknown = await response.json();

      if (!Array.isArray(data) || !data.every(isPaper)) {
        throw new Error("FastAPI devolvió un formato inesperado");
      }

      setPapers(data);
    } catch (requestError) {
      console.error(requestError);
      setError(
        "No fue posible obtener las publicaciones. Intenta nuevamente en unos momentos.",
      );
    } finally {
      requestInProgress.current = false;
      setIsLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-cocid-white px-4 py-12 text-cocid-navy sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-8">
        <header className="space-y-3">
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            Buscador de artículos científicos
          </h1>
          <p className="max-w-2xl text-lg leading-8 text-cocid-graphite">
            Escribe un tema y consulta publicaciones académicas para apoyar tu
            investigación.
          </p>
          <p className="text-sm text-cocid-graphite">
            Fuente de publicaciones: OpenAlex
          </p>
        </header>

        <form
          className="rounded-2xl border border-cocid-graphite bg-cocid-white p-5"
          onSubmit={handleSubmit}
        >
          <label
            className="mb-2 block text-sm font-semibold text-cocid-navy"
            htmlFor="topic"
          >
            Tema de investigación
          </label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              aria-describedby="topic-help"
              id="topic"
              className="min-w-0 flex-1 rounded-xl border border-cocid-graphite bg-cocid-white px-4 py-3 text-cocid-navy outline-none transition placeholder:text-cocid-graphite focus:border-cocid-tech-blue focus:ring-4 focus:ring-cocid-tech-blue"
              name="topic"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ej. inteligencia artificial en educación"
              required
              type="search"
              value={query}
            />
            <button
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-cocid-tech-blue px-6 py-3 font-semibold text-cocid-white transition hover:bg-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue disabled:cursor-not-allowed disabled:bg-cocid-graphite"
              disabled={isLoading}
              type="submit"
            >
              {isLoading && (
                <span
                  aria-hidden="true"
                  className="h-4 w-4 animate-spin rounded-full border-2 border-cocid-white border-t-cocid-navy"
                />
              )}
              {isLoading ? "Buscando..." : "Buscar"}
            </button>
          </div>
          <p className="sr-only" id="topic-help">
            Escribe palabras clave y presiona Buscar.
          </p>

          <fieldset
            className="mt-5 border-t border-cocid-graphite pt-5"
            disabled={isLoading}
          >
            <legend className="px-2 text-sm font-semibold text-cocid-navy">
              Filtros opcionales
            </legend>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <label className="text-sm text-cocid-graphite">
                <span className="mb-1 block font-medium">Desde el año</span>
                <input
                  className="w-full rounded-lg border border-cocid-graphite bg-cocid-white px-3 py-2 text-cocid-navy outline-none placeholder:text-cocid-graphite focus:border-cocid-tech-blue focus:ring-4 focus:ring-cocid-tech-blue"
                  max="2100"
                  min="1000"
                  name="from-year"
                  onChange={(event) => setFromYear(event.target.value)}
                  placeholder="Ej. 2020"
                  type="number"
                  value={fromYear}
                />
              </label>
              <label className="text-sm text-cocid-graphite">
                <span className="mb-1 block font-medium">Hasta el año</span>
                <input
                  className="w-full rounded-lg border border-cocid-graphite bg-cocid-white px-3 py-2 text-cocid-navy outline-none placeholder:text-cocid-graphite focus:border-cocid-tech-blue focus:ring-4 focus:ring-cocid-tech-blue"
                  max="2100"
                  min="1000"
                  name="to-year"
                  onChange={(event) => setToYear(event.target.value)}
                  placeholder="Ej. 2026"
                  type="number"
                  value={toYear}
                />
              </label>
              <label className="text-sm text-cocid-graphite">
                <span className="mb-1 block font-medium">
                  Tipo de publicación
                </span>
                <select
                  className="w-full rounded-lg border border-cocid-graphite bg-cocid-white px-3 py-2 text-cocid-navy outline-none focus:border-cocid-tech-blue focus:ring-4 focus:ring-cocid-tech-blue"
                  name="publication-type"
                  onChange={(event) =>
                    setPublicationType(
                      event.target.value as PublicationTypeFilter,
                    )
                  }
                  value={publicationType}
                >
                  <option value="">Todos</option>
                  {PUBLICATION_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm text-cocid-graphite">
                <span className="mb-1 block font-medium">Acceso</span>
                <select
                  className="w-full rounded-lg border border-cocid-graphite bg-cocid-white px-3 py-2 text-cocid-navy outline-none focus:border-cocid-tech-blue focus:ring-4 focus:ring-cocid-tech-blue"
                  name="open-access"
                  onChange={(event) =>
                    setOpenAccess(event.target.value as OpenAccessFilter)
                  }
                  value={openAccess}
                >
                  <option value="">Todos</option>
                  <option value="true">Acceso abierto</option>
                  <option value="false">Acceso cerrado</option>
                </select>
              </label>
            </div>
            <div className="mt-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button
                className="rounded-lg border border-cocid-tech-blue bg-cocid-white px-3 py-2 text-sm font-semibold text-cocid-tech-blue transition hover:bg-cocid-tech-blue hover:text-cocid-white focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue disabled:cursor-not-allowed disabled:border-cocid-graphite disabled:bg-cocid-white disabled:text-cocid-graphite"
                disabled={!hasActiveFilters || isLoading}
                onClick={clearFilters}
                type="button"
              >
                Limpiar filtros
              </button>

              {hasActiveFilters && (
                <div
                  aria-label="Filtros activos"
                  aria-live="polite"
                  className="flex flex-wrap items-center gap-2 text-sm text-cocid-graphite"
                >
                  <span className="font-medium">
                    {activeFilters.length}{" "}
                    {activeFilters.length === 1
                      ? "filtro aplicado:"
                      : "filtros aplicados:"}
                  </span>
                  <ul className="flex flex-wrap gap-2">
                    {activeFilters.map((filter) => (
                      <li
                        className="rounded-full bg-cocid-turquoise px-3 py-1 text-xs font-medium text-cocid-navy"
                        key={filter}
                      >
                        {filter}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </fieldset>
        </form>

        <section aria-busy={isLoading} aria-live="polite">
          {error && (
            <p
              className="rounded-xl border border-cocid-gold bg-cocid-white p-4 text-cocid-graphite"
              role="alert"
            >
              {error}
            </p>
          )}

          {!error && isLoading && (
            <div
              className="flex items-center gap-3 rounded-xl border border-cocid-tech-blue bg-cocid-white p-4 text-cocid-navy"
              role="status"
            >
              <span
                aria-hidden="true"
                className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-cocid-graphite border-t-cocid-tech-blue"
              />
              <p>Buscando publicaciones científicas...</p>
            </div>
          )}

          {!error && !isLoading && hasSearched && papers.length === 0 && (
            <div className="rounded-xl border border-cocid-graphite bg-cocid-white p-5 text-cocid-graphite">
              <p className="font-semibold text-cocid-navy">
                No se encontraron publicaciones.
              </p>
              <p className="mt-1">
                Prueba con términos más generales o modifica los filtros.
              </p>
            </div>
          )}

          {!error && papers.length > 0 && (
            <div className="space-y-4">
              <h2 className="text-xl font-semibold">
                Resultados ({papers.length})
              </h2>
              <ul className="space-y-4">
                {papers.map((paper, index) => {
                  const openAccessLabel = getOpenAccessLabel(paper);
                  const doiUrl = getSafeExternalUrl(paper.doi);

                  return (
                    <li
                      className="min-w-0 rounded-2xl border border-cocid-graphite bg-cocid-white p-5"
                      key={paper.id ?? paper.doi ?? `${paper.title}-${index}`}
                    >
                      <article className="space-y-3">
                        <div className="flex flex-col items-start gap-2 sm:flex-row sm:justify-between">
                          <h3 className="min-w-0 break-words text-xl font-semibold leading-7 text-cocid-navy">
                            {displayValue(paper.title, "Título no disponible")}
                          </h3>
                          {openAccessLabel && (
                            <span
                              className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${getOpenAccessClassName(paper)}`}
                            >
                              {openAccessLabel}
                            </span>
                          )}
                        </div>
                        <dl className="grid gap-3 text-sm text-cocid-graphite sm:grid-cols-2">
                          <div className="sm:col-span-2">
                            <dt className="font-semibold text-cocid-navy">
                              Autores
                            </dt>
                            <dd className="break-words">
                              {displayAuthors(paper.authors, 6)}
                            </dd>
                          </div>
                          <div>
                            <dt className="font-semibold text-cocid-navy">Año</dt>
                            <dd>{paper.year ?? "Año no disponible"}</dd>
                          </div>
                          <div>
                            <dt className="font-semibold text-cocid-navy">Citas</dt>
                            <dd>{paper.citations ?? "Citas no disponibles"}</dd>
                          </div>
                          <div className="sm:col-span-2">
                            <dt className="font-semibold text-cocid-navy">
                              Revista o fuente
                            </dt>
                            <dd className="break-words">
                              {displayValue(
                                paper.source,
                                "Fuente no disponible",
                              )}
                            </dd>
                          </div>
                          <div className="sm:col-span-2">
                            <dt className="font-semibold text-cocid-navy">DOI</dt>
                            <dd className="break-all">
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
                        {paper.openalex_id && (
                          <Link
                            className="inline-flex rounded-lg bg-cocid-tech-blue px-4 py-2 text-sm font-semibold text-cocid-white transition hover:bg-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue"
                            href={`/papers/${paper.openalex_id}?from=results`}
                            onClick={preserveSearchForDetails}
                          >
                            Ver detalles
                          </Link>
                        )}
                      </article>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
