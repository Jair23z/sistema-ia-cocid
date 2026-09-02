import {
  isBatchAnalysisResponse,
  type BatchAnalysisErrorCode,
  type BatchAnalysisResponse,
} from "./batch-analysis";
import {
  MAX_BATCH_SELECTION,
  MIN_BATCH_SELECTION,
  isSelectableOpenAlexId,
} from "./batch-selection";
import { API_BASE_URL } from "./papers";

export type ComparisonStatus =
  | "completed"
  | "insufficient_comparable_papers";

export type ComparisonPaperReference = {
  openalex_id: string;
  title: string | null;
  doi: string | null;
  year: number | null;
  source: string | null;
};

export type ExcludedComparisonPaper = {
  openalex_id: string;
  reason: "analysis_error" | "insufficient_evidence";
  message: string;
  error_code: BatchAnalysisErrorCode | null;
};

export type ComparativePoint = {
  text: string;
  supporting_papers: string[];
};

export type ComparativeScientificAnalysis = {
  summary: string;
  common_points: ComparativePoint[];
  differences: ComparativePoint[];
  trends: ComparativePoint[];
  research_gaps: ComparativePoint[];
};

export type BatchComparisonResponse = {
  batch_analysis: BatchAnalysisResponse;
  comparison_status: ComparisonStatus;
  considered_count: number;
  considered_papers: ComparisonPaperReference[];
  excluded_papers: ExcludedComparisonPaper[];
  comparison: ComparativeScientificAnalysis | null;
};

const COMPARISON_RESPONSE_KEYS = [
  "batch_analysis",
  "comparison_status",
  "considered_count",
  "considered_papers",
  "excluded_papers",
  "comparison",
];
const SCOPED_GAP_PREFIXES = [
  "entre las publicaciones analizadas",
  "en el conjunto seleccionado",
  "esta muestra presenta poca evidencia sobre",
];
const PROHIBITED_UNIVERSAL_CLAIMS = [
  /\b(?:nunca|jamás)\s+se\s+ha\s+(?:estudiado|investigado|analizado)\b/u,
  /\bno\s+existen?\s+(?:estudios|investigaciones|evidencia|literatura)\b/u,
  /\bnadie\s+ha\s+(?:investigado|estudiado|analizado)\b/u,
  /\bning[uú]n(?:a)?\s+(?:estudio|investigación|publicación)\s+(?:ha|aborda|analiza|estudia)\b/u,
];
const BATCH_ANALYSIS_ERROR_CODES = new Set<BatchAnalysisErrorCode>([
  "paper_not_found",
  "openalex_timeout",
  "openalex_unavailable",
  "invalid_paper_data",
  "analysis_not_configured",
  "analysis_authentication_failed",
  "analysis_timeout",
  "analysis_rate_limited",
  "invalid_analysis_response",
  "analysis_unavailable",
]);

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actualKeys = Object.keys(value);
  return (
    actualKeys.length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || Number.isInteger(value);
}

function isNonEmptyText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isComparisonPaperReference(
  value: unknown,
): value is ComparisonPaperReference {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const paper = value as Record<string, unknown>;
  return (
    hasExactKeys(paper, ["openalex_id", "title", "doi", "year", "source"]) &&
    typeof paper.openalex_id === "string" &&
    isSelectableOpenAlexId(paper.openalex_id) &&
    isNullableString(paper.title) &&
    isNullableString(paper.doi) &&
    isNullableNumber(paper.year) &&
    isNullableString(paper.source)
  );
}

function isExcludedComparisonPaper(
  value: unknown,
): value is ExcludedComparisonPaper {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const paper = value as Record<string, unknown>;
  if (
    !hasExactKeys(paper, [
      "openalex_id",
      "reason",
      "message",
      "error_code",
    ]) ||
    typeof paper.openalex_id !== "string" ||
    !isSelectableOpenAlexId(paper.openalex_id) ||
    !isNonEmptyText(paper.message)
  ) {
    return false;
  }

  if (paper.reason === "analysis_error") {
    return (
      typeof paper.error_code === "string" &&
      BATCH_ANALYSIS_ERROR_CODES.has(
        paper.error_code as BatchAnalysisErrorCode,
      )
    );
  }

  return paper.reason === "insufficient_evidence" && paper.error_code === null;
}

function isComparativePoint(
  value: unknown,
  consideredIds: Set<string>,
  minimumReferences: number,
): value is ComparativePoint {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const point = value as Record<string, unknown>;
  if (
    !hasExactKeys(point, ["text", "supporting_papers"]) ||
    !isNonEmptyText(point.text) ||
    !Array.isArray(point.supporting_papers) ||
    point.supporting_papers.length < minimumReferences ||
    point.supporting_papers.length > MAX_BATCH_SELECTION ||
    !point.supporting_papers.every(
      (paperId) =>
        typeof paperId === "string" &&
        consideredIds.has(paperId) &&
        isSelectableOpenAlexId(paperId),
    )
  ) {
    return false;
  }

  return new Set(point.supporting_papers).size === point.supporting_papers.length;
}

function containsUniversalClaim(texts: string[]): boolean {
  return texts.some((text) =>
    PROHIBITED_UNIVERSAL_CLAIMS.some((pattern) =>
      pattern.test(text.toLocaleLowerCase("es")),
    ),
  );
}

function isComparativeScientificAnalysis(
  value: unknown,
  consideredIds: Set<string>,
): value is ComparativeScientificAnalysis {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const analysis = value as Record<string, unknown>;
  if (
    !hasExactKeys(analysis, [
      "summary",
      "common_points",
      "differences",
      "trends",
      "research_gaps",
    ]) ||
    !isNonEmptyText(analysis.summary)
  ) {
    return false;
  }

  const comparativeCollections = [
    analysis.common_points,
    analysis.differences,
    analysis.trends,
  ];
  if (
    !comparativeCollections.every(
      (points) =>
        Array.isArray(points) &&
        points.every((point) => isComparativePoint(point, consideredIds, 2)),
    ) ||
    !Array.isArray(analysis.research_gaps) ||
    !analysis.research_gaps.every((point) =>
      isComparativePoint(point, consideredIds, 1),
    )
  ) {
    return false;
  }

  const researchGaps = analysis.research_gaps as ComparativePoint[];
  if (
    researchGaps.some((gap) =>
      !SCOPED_GAP_PREFIXES.some((prefix) =>
        gap.text.toLocaleLowerCase("es").startsWith(prefix),
      ),
    )
  ) {
    return false;
  }

  const points = [
    ...(analysis.common_points as ComparativePoint[]),
    ...(analysis.differences as ComparativePoint[]),
    ...(analysis.trends as ComparativePoint[]),
    ...researchGaps,
  ];
  return !containsUniversalClaim([
    analysis.summary as string,
    ...points.map((point) => point.text),
  ]);
}

export function isBatchComparisonResponse(
  value: unknown,
  expectedPaperIds?: string[],
): value is BatchComparisonResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const response = value as Record<string, unknown>;
  if (
    !hasExactKeys(response, COMPARISON_RESPONSE_KEYS) ||
    !isBatchAnalysisResponse(response.batch_analysis, expectedPaperIds) ||
    (response.comparison_status !== "completed" &&
      response.comparison_status !== "insufficient_comparable_papers") ||
    !Number.isInteger(response.considered_count) ||
    Number(response.considered_count) < 0 ||
    !Array.isArray(response.considered_papers) ||
    !response.considered_papers.every(isComparisonPaperReference) ||
    !Array.isArray(response.excluded_papers) ||
    !response.excluded_papers.every(isExcludedComparisonPaper)
  ) {
    return false;
  }

  const consideredPapers =
    response.considered_papers as ComparisonPaperReference[];
  const excludedPapers = response.excluded_papers as ExcludedComparisonPaper[];
  const consideredIds = new Set(
    consideredPapers.map((paper) => paper.openalex_id),
  );
  const excludedIds = new Set(
    excludedPapers.map((paper) => paper.openalex_id),
  );
  const batchIds = (
    response.batch_analysis as BatchAnalysisResponse
  ).results.map((result) => result.openalex_id);
  const batchStatusById = new Map(
    (response.batch_analysis as BatchAnalysisResponse).results.map((result) => [
      result.openalex_id,
      result.status,
    ]),
  );

  if (
    response.considered_count !== consideredPapers.length ||
    consideredIds.size !== consideredPapers.length ||
    excludedIds.size !== excludedPapers.length ||
    consideredPapers.some((paper) => excludedIds.has(paper.openalex_id)) ||
    consideredIds.size + excludedIds.size !== batchIds.length ||
    batchIds.some(
      (paperId) => !consideredIds.has(paperId) && !excludedIds.has(paperId),
    ) ||
    consideredPapers.some(
      (paper) => batchStatusById.get(paper.openalex_id) !== "success",
    ) ||
    excludedPapers.some((paper) =>
      paper.reason === "analysis_error"
        ? batchStatusById.get(paper.openalex_id) !== "error"
        : batchStatusById.get(paper.openalex_id) !== "success",
    )
  ) {
    return false;
  }

  if (response.comparison_status === "completed") {
    return (
      consideredPapers.length >= MIN_BATCH_SELECTION &&
      isComparativeScientificAnalysis(response.comparison, consideredIds)
    );
  }

  return consideredPapers.length < MIN_BATCH_SELECTION && response.comparison === null;
}

export async function requestBatchComparison(
  paperIds: string[],
  fetchImplementation: typeof fetch = fetch,
): Promise<BatchComparisonResponse> {
  const uniquePaperIds = [...new Set(paperIds)];
  if (
    uniquePaperIds.length < MIN_BATCH_SELECTION ||
    uniquePaperIds.length > MAX_BATCH_SELECTION ||
    !uniquePaperIds.every(isSelectableOpenAlexId)
  ) {
    throw new Error("invalid-batch-comparison-selection");
  }

  const response = await fetchImplementation(
    `${API_BASE_URL}/papers/batch-comparison`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ paper_ids: uniquePaperIds }),
    },
  );

  if (!response.ok) {
    throw new Error("batch-comparison-request-failed");
  }

  const data: unknown = await response.json();
  if (!isBatchComparisonResponse(data, uniquePaperIds)) {
    throw new Error("invalid-batch-comparison-response");
  }

  return data;
}
