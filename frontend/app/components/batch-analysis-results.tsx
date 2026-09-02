import type { BatchAnalysisResponse } from "@/app/lib/batch-analysis";
import { displayValue, type Paper } from "@/app/lib/papers";


type BatchAnalysisResultsProps = {
  response: BatchAnalysisResponse;
  papers: Paper[];
};

export function BatchAnalysisResults({
  response,
  papers,
}: BatchAnalysisResultsProps) {
  function getPaperTitle(openAlexId: string) {
    const paper = papers.find((item) => item.openalex_id === openAlexId);
    return displayValue(paper?.title ?? null, "Título no disponible");
  }

  return (
    <section
      aria-label="Resultados del análisis por lote"
      className="space-y-4 rounded-2xl border border-cocid-tech-blue bg-cocid-white p-5"
    >
      <div className="space-y-1">
        <h3 className="text-xl font-semibold text-cocid-navy">
          Resultados individuales del lote
        </h3>
        <p className="text-sm text-cocid-graphite" role="status">
          {response.success_count} de {response.requested_count} publicaciones
          procesadas correctamente. Esta vista todavía no compara las
          publicaciones.
        </p>
      </div>

      <ul className="space-y-3">
        {response.results.map((result) => (
          <li
            className={`rounded-xl border bg-cocid-white p-4 ${
              result.status === "success"
                ? "border-cocid-turquoise"
                : "border-cocid-gold"
            }`}
            key={result.openalex_id}
          >
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <p className="break-words font-semibold text-cocid-navy">
                  {getPaperTitle(result.openalex_id)}
                </p>
                <p className="text-xs text-cocid-graphite">
                  {result.openalex_id}
                </p>
              </div>
              <span
                className={`w-fit shrink-0 rounded-full px-3 py-1 text-xs font-semibold text-cocid-navy ${
                  result.status === "success"
                    ? "bg-cocid-turquoise"
                    : "bg-cocid-gold"
                }`}
              >
                {result.status === "success" ? "Completado" : "No completado"}
              </span>
            </div>

            {result.status === "error" ? (
              <p className="mt-3 text-sm text-cocid-graphite" role="alert">
                {result.error.message}
              </p>
            ) : (
              <div className="mt-4 space-y-4 text-sm text-cocid-graphite">
                <div>
                  <h4 className="font-semibold text-cocid-navy">Objetivo</h4>
                  <p className="break-words">{result.analysis.objective}</p>
                </div>
                <div>
                  <h4 className="font-semibold text-cocid-navy">Metodología</h4>
                  <p className="break-words">{result.analysis.methodology}</p>
                </div>
                <div>
                  <h4 className="font-semibold text-cocid-navy">Resultados</h4>
                  <p className="break-words">{result.analysis.results}</p>
                </div>
                <div>
                  <h4 className="font-semibold text-cocid-navy">Conclusiones</h4>
                  <p className="break-words">{result.analysis.conclusions}</p>
                </div>
                <div>
                  <h4 className="font-semibold text-cocid-navy">
                    Hallazgos principales
                  </h4>
                  {result.analysis.findings.length > 0 ? (
                    <ul className="mt-2 list-disc space-y-1 pl-5 marker:text-cocid-turquoise">
                      {result.analysis.findings.map((finding, index) => (
                        <li className="break-words" key={`${finding}-${index}`}>
                          {finding}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>No se identificaron hallazgos con la evidencia disponible.</p>
                  )}
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
