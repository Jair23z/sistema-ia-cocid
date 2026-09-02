import { API_BASE_URL } from "./papers";

export type ScientificAnalysis = {
  objective: string;
  methodology: string;
  results: string;
  conclusions: string;
  findings: string[];
};

const ANALYSIS_TEXT_FIELDS = [
  "objective",
  "methodology",
  "results",
  "conclusions",
] as const;

export function isScientificAnalysis(
  value: unknown,
): value is ScientificAnalysis {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const analysis = value as Record<string, unknown>;
  const hasValidTextFields = ANALYSIS_TEXT_FIELDS.every((field) => {
    const fieldValue = analysis[field];

    return (
      typeof fieldValue === "string" &&
      fieldValue.trim().length > 0 &&
      fieldValue.length <= 2000
    );
  });
  const findings = analysis.findings;

  return (
    Object.keys(analysis).length === 5 &&
    hasValidTextFields &&
    Array.isArray(findings) &&
    findings.length <= 10 &&
    findings.every(
      (finding) =>
        typeof finding === "string" &&
        finding.trim().length > 0 &&
        finding.length <= 1000,
    )
  );
}

export async function requestScientificAnalysis(
  openAlexId: string,
  fetchImplementation: typeof fetch = fetch,
): Promise<ScientificAnalysis> {
  const response = await fetchImplementation(
    `${API_BASE_URL}/papers/${encodeURIComponent(openAlexId)}/analysis`,
    {
      method: "POST",
      headers: { Accept: "application/json" },
    },
  );

  if (!response.ok) {
    throw new Error("analysis-request-failed");
  }

  const data: unknown = await response.json();

  if (!isScientificAnalysis(data)) {
    throw new Error("invalid-analysis-response");
  }

  return data;
}
