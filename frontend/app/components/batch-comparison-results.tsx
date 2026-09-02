import Link from "next/link";

import type {
  BatchComparisonResponse,
  ComparativePoint,
  ComparisonPaperReference,
} from "@/app/lib/batch-comparison";
import type { ScientificAnalysis } from "@/app/lib/scientific-analysis";
import {
  displayValue,
  formatDoi,
  getSafeExternalUrl,
  type Paper,
} from "@/app/lib/papers";

type BatchComparisonResultsProps = {
  response: BatchComparisonResponse;
  papers: Paper[];
};

type MatrixField = keyof Pick<
  ScientificAnalysis,
  "objective" | "methodology" | "results" | "conclusions"
>;

const MATRIX_ROWS: ReadonlyArray<{ field: MatrixField; label: string }> = [
  { field: "objective", label: "Objetivo" },
  { field: "methodology", label: "Metodología" },
  { field: "results", label: "Resultados" },
  { field: "conclusions", label: "Conclusiones" },
];

function PaperReferenceBadges({
  paperIds,
  paperLabels,
}: {
  paperIds: string[];
  paperLabels: Map<string, string>;
}) {
  return (
    <ul
      aria-label="Publicaciones que respaldan esta observación"
      className="mt-2 flex flex-wrap gap-2"
    >
      {paperIds.map((paperId) => (
        <li key={paperId}>
          <Link
            className="inline-flex rounded-full bg-cocid-turquoise px-3 py-1 text-xs font-semibold text-cocid-navy focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue"
            href={`/papers/${paperId}?from=results`}
            title={paperId}
          >
            {paperLabels.get(paperId) ?? paperId}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function ComparisonPoints({
  heading,
  points,
  paperLabels,
  accent,
}: {
  heading: string;
  points: ComparativePoint[];
  paperLabels: Map<string, string>;
  accent: "blue" | "gold" | "turquoise";
}) {
  const borderClass = {
    blue: "border-cocid-tech-blue",
    gold: "border-cocid-gold",
    turquoise: "border-cocid-turquoise",
  }[accent];

  return (
    <section className="space-y-3" aria-label={heading}>
      <h3 className="text-xl font-semibold text-cocid-navy">{heading}</h3>
      {points.length > 0 ? (
        <ul className="space-y-3">
          {points.map((point, index) => (
            <li
              className={`rounded-xl border bg-cocid-white p-4 ${borderClass}`}
              key={`${heading}-${index}`}
            >
              <p className="break-words text-cocid-graphite">{point.text}</p>
              <PaperReferenceBadges
                paperIds={point.supporting_papers}
                paperLabels={paperLabels}
              />
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-xl border border-cocid-graphite bg-cocid-white p-4 text-cocid-graphite">
          No se identificaron elementos sustentados para esta sección.
        </p>
      )}
    </section>
  );
}

function ConsideredPapers({
  papers,
}: {
  papers: ComparisonPaperReference[];
}) {
  return (
    <section className="space-y-3" aria-label="Publicaciones consideradas">
      <h3 className="text-xl font-semibold text-cocid-navy">
        Publicaciones consideradas ({papers.length})
      </h3>
      <ol className="grid gap-3 sm:grid-cols-2">
        {papers.map((paper, index) => {
          const doiUrl = getSafeExternalUrl(paper.doi);

          return (
            <li
              className="rounded-xl border border-cocid-turquoise bg-cocid-white p-4"
              key={paper.openalex_id}
            >
              <p className="text-xs font-semibold text-cocid-turquoise">
                P{index + 1} · {paper.openalex_id}
              </p>
              <p className="mt-1 break-words font-semibold text-cocid-navy">
                {displayValue(paper.title, "Título no disponible")}
              </p>
              <dl className="mt-3 space-y-1 text-sm text-cocid-graphite">
                <div>
                  <dt className="inline font-semibold text-cocid-navy">Año: </dt>
                  <dd className="inline">{paper.year ?? "No disponible"}</dd>
                </div>
                <div>
                  <dt className="inline font-semibold text-cocid-navy">
                    Fuente:{" "}
                  </dt>
                  <dd className="inline">
                    {displayValue(paper.source, "No disponible")}
                  </dd>
                </div>
                {paper.doi && (
                  <div>
                    <dt className="inline font-semibold text-cocid-navy">
                      DOI:{" "}
                    </dt>
                    <dd className="inline break-all">
                      {doiUrl ? (
                        <a
                          className="text-cocid-tech-blue underline decoration-cocid-tech-blue underline-offset-4 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue"
                          href={doiUrl}
                          rel="noopener noreferrer"
                          target="_blank"
                        >
                          {formatDoi(paper.doi)}
                        </a>
                      ) : (
                        formatDoi(paper.doi)
                      )}
                    </dd>
                  </div>
                )}
              </dl>
              <Link
                className="mt-3 inline-flex rounded-lg bg-cocid-tech-blue px-3 py-2 text-sm font-semibold text-cocid-white focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue"
                href={`/papers/${paper.openalex_id}?from=results`}
              >
                Ver detalle individual
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export function BatchComparisonResults({
  response,
  papers,
}: BatchComparisonResultsProps) {
  const successfulAnalyses = new Map(
    response.batch_analysis.results.flatMap((result) =>
      result.status === "success"
        ? [[result.openalex_id, result.analysis] as const]
        : [],
    ),
  );
  const paperLabels = new Map(
    response.considered_papers.map((paper, index) => [
      paper.openalex_id,
      `P${index + 1}`,
    ]),
  );

  return (
    <section
      aria-label="Comparación científica de publicaciones"
      className="space-y-8 rounded-2xl border border-cocid-tech-blue bg-cocid-white p-5"
    >
      <div className="space-y-1">
        <h2 className="text-2xl font-semibold text-cocid-navy">
          Análisis comparativo
        </h2>
        <p className="text-sm text-cocid-graphite">
          Comparación de las publicaciones seleccionadas con trazabilidad hacia
          cada análisis individual.
        </p>
      </div>

      {response.comparison_status === "insufficient_comparable_papers" ? (
        <div
          className="rounded-xl border border-cocid-gold bg-cocid-white p-4 text-cocid-graphite"
          role="status"
        >
          <h3 className="font-semibold text-cocid-navy">
            No hay suficientes publicaciones comparables
          </h3>
          <p className="mt-1">
            No existen suficientes publicaciones con información para generar
            una comparación. Se necesitan al menos dos análisis válidos.
          </p>
        </div>
      ) : (
        response.comparison && (
          <>
            <section className="space-y-2" aria-label="Resumen general">
              <h3 className="text-xl font-semibold text-cocid-navy">
                Resumen general
              </h3>
              <p className="rounded-xl border border-cocid-gold bg-cocid-white p-4 leading-7 text-cocid-graphite">
                {response.comparison.summary}
              </p>
            </section>

            <ConsideredPapers papers={response.considered_papers} />

            <section className="space-y-3" aria-label="Matriz comparativa">
              <div>
                <h3 className="text-xl font-semibold text-cocid-navy">
                  Matriz comparativa
                </h3>
                <p className="text-sm text-cocid-graphite">
                  La matriz se construye directamente con los análisis
                  individuales, sin solicitudes adicionales de inteligencia
                  artificial.
                </p>
              </div>
              <div
                className="overflow-x-auto rounded-xl border border-cocid-graphite bg-cocid-white"
                data-responsive-table="horizontal-scroll"
              >
                <table className="w-full min-w-[48rem] border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-cocid-graphite">
                      <th
                        className="sticky left-0 z-10 min-w-36 border-r border-cocid-graphite bg-cocid-white p-3 font-semibold text-cocid-navy"
                        scope="col"
                      >
                        Campo
                      </th>
                      {response.considered_papers.map((paper, index) => (
                        <th
                          className="min-w-64 border-r border-cocid-graphite p-3 align-top font-semibold text-cocid-navy last:border-r-0"
                          key={paper.openalex_id}
                          scope="col"
                        >
                          <span className="block text-xs text-cocid-turquoise">
                            P{index + 1}
                          </span>
                          <span className="block break-words">
                            {displayValue(paper.title, paper.openalex_id)}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {MATRIX_ROWS.map((row) => (
                      <tr
                        className="border-b border-cocid-graphite last:border-b-0"
                        key={row.field}
                      >
                        <th
                          className="sticky left-0 z-10 border-r border-cocid-graphite bg-cocid-white p-3 align-top font-semibold text-cocid-navy"
                          scope="row"
                        >
                          {row.label}
                        </th>
                        {response.considered_papers.map((paper) => (
                          <td
                            className="min-w-64 border-r border-cocid-graphite p-3 align-top leading-6 text-cocid-graphite last:border-r-0"
                            key={`${row.field}-${paper.openalex_id}`}
                          >
                            {successfulAnalyses.get(paper.openalex_id)?.[
                              row.field
                            ] ?? "Información no disponible"}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <ComparisonPoints
              accent="turquoise"
              heading="Coincidencias"
              paperLabels={paperLabels}
              points={response.comparison.common_points}
            />
            <ComparisonPoints
              accent="blue"
              heading="Diferencias"
              paperLabels={paperLabels}
              points={response.comparison.differences}
            />
            <ComparisonPoints
              accent="turquoise"
              heading="Tendencias"
              paperLabels={paperLabels}
              points={response.comparison.trends}
            />
            <section className="space-y-3" aria-label="Brechas del conjunto">
              <ComparisonPoints
                accent="gold"
                heading="Brechas del conjunto"
                paperLabels={paperLabels}
                points={response.comparison.research_gaps}
              />
              <p className="rounded-xl border border-cocid-gold bg-cocid-white p-4 text-sm text-cocid-graphite">
                Las brechas identificadas corresponden únicamente al conjunto
                de publicaciones analizado y no representan necesariamente toda
                la literatura disponible.
              </p>
            </section>
          </>
        )
      )}

      {response.comparison_status === "insufficient_comparable_papers" &&
        response.considered_papers.length > 0 && (
          <ConsideredPapers papers={response.considered_papers} />
        )}

      {response.excluded_papers.length > 0 && (
        <section className="space-y-3" aria-label="Publicaciones excluidas">
          <h3 className="text-xl font-semibold text-cocid-navy">
            Publicaciones excluidas ({response.excluded_papers.length})
          </h3>
          <ul className="space-y-3">
            {response.excluded_papers.map((excludedPaper) => {
              const matchingPaper = papers.find(
                (paper) => paper.openalex_id === excludedPaper.openalex_id,
              );

              return (
                <li
                  className="rounded-xl border border-cocid-gold bg-cocid-white p-4"
                  key={excludedPaper.openalex_id}
                >
                  <p className="break-words font-semibold text-cocid-navy">
                    {displayValue(
                      matchingPaper?.title ?? null,
                      excludedPaper.openalex_id,
                    )}
                  </p>
                  <p className="text-xs text-cocid-graphite">
                    {excludedPaper.openalex_id}
                  </p>
                  <p className="mt-2 text-sm text-cocid-graphite">
                    {excludedPaper.message}
                  </p>
                  <Link
                    className="mt-3 inline-flex text-sm font-semibold text-cocid-tech-blue underline decoration-cocid-tech-blue underline-offset-4 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cocid-tech-blue"
                    href={`/papers/${excludedPaper.openalex_id}?from=results`}
                  >
                    Ver detalle individual
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </section>
  );
}
