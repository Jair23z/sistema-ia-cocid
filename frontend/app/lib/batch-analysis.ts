import { API_BASE_URL } from "./papers";
import {
  isScientificAnalysis,
  type ScientificAnalysis,
} from "./scientific-analysis";

import {
  MAX_BATCH_SELECTION,
  MIN_BATCH_SELECTION,
  isSelectableOpenAlexId,
} from "./batch-selection";

export type BatchAnalysisErrorCode =
  | "paper_not_found"
  | "openalex_timeout"
  | "openalex_unavailable"
  | "invalid_paper_data"
  | "analysis_not_configured"
  | "analysis_authentication_failed"
  | "analysis_timeout"
  | "analysis_rate_limited"
  | "invalid_analysis_response"
  | "analysis_unavailable";

export type BatchAnalysisError = {
  code: BatchAnalysisErrorCode;
  message: string;
};

export type BatchAnalysisSuccessItem = {
  openalex_id: string;
  status: "success";
  analysis: ScientificAnalysis;
  error: null;
};

export type BatchAnalysisErrorItem = {
  openalex_id: string;
  status: "error";
  analysis: null;
  error: BatchAnalysisError;
};

export type BatchPaperAnalysisResult =
  | BatchAnalysisSuccessItem
  | BatchAnalysisErrorItem;

export type BatchAnalysisResponse = {
  requested_count: number;
  processed_count: number;
  success_count: number;
  error_count: number;
  results: BatchPaperAnalysisResult[];
};

const BATCH_ERROR_CODES = new Set<BatchAnalysisErrorCode>([
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

function isBatchAnalysisError(value: unknown): value is BatchAnalysisError {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const error = value as Record<string, unknown>;
  return (
    hasExactKeys(error, ["code", "message"]) &&
    typeof error.code === "string" &&
    BATCH_ERROR_CODES.has(error.code as BatchAnalysisErrorCode) &&
    typeof error.message === "string" &&
    error.message.trim().length > 0 &&
    error.message.length <= 300
  );
}

function isBatchResult(value: unknown): value is BatchPaperAnalysisResult {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const result = value as Record<string, unknown>;
  if (
    !hasExactKeys(result, ["openalex_id", "status", "analysis", "error"]) ||
    typeof result.openalex_id !== "string" ||
    !isSelectableOpenAlexId(result.openalex_id)
  ) {
    return false;
  }

  if (result.status === "success") {
    return result.error === null && isScientificAnalysis(result.analysis);
  }

  if (result.status === "error") {
    return result.analysis === null && isBatchAnalysisError(result.error);
  }

  return false;
}

function isCount(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 0;
}

export function isBatchAnalysisResponse(
  value: unknown,
  expectedPaperIds?: string[],
): value is BatchAnalysisResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const response = value as Record<string, unknown>;
  if (
    !hasExactKeys(response, [
      "requested_count",
      "processed_count",
      "success_count",
      "error_count",
      "results",
    ]) ||
    !isCount(response.requested_count) ||
    !isCount(response.processed_count) ||
    !isCount(response.success_count) ||
    !isCount(response.error_count) ||
    !Array.isArray(response.results) ||
    response.results.length < MIN_BATCH_SELECTION ||
    response.results.length > MAX_BATCH_SELECTION ||
    !response.results.every(isBatchResult)
  ) {
    return false;
  }

  const results = response.results as BatchPaperAnalysisResult[];
  const resultIds = results.map((result) => result.openalex_id);
  const successCount = results.filter(
    (result) => result.status === "success",
  ).length;
  const errorCount = results.length - successCount;

  if (
    new Set(resultIds).size !== resultIds.length ||
    response.requested_count !== results.length ||
    response.processed_count !== results.length ||
    response.success_count !== successCount ||
    response.error_count !== errorCount
  ) {
    return false;
  }

  return (
    expectedPaperIds === undefined ||
    (expectedPaperIds.length === resultIds.length &&
      expectedPaperIds.every((paperId, index) => paperId === resultIds[index]))
  );
}

export async function requestBatchScientificAnalysis(
  paperIds: string[],
  fetchImplementation: typeof fetch = fetch,
): Promise<BatchAnalysisResponse> {
  const uniquePaperIds = listUniquePaperIds(paperIds);
  if (
    uniquePaperIds.length < MIN_BATCH_SELECTION ||
    uniquePaperIds.length > MAX_BATCH_SELECTION ||
    !uniquePaperIds.every(isSelectableOpenAlexId)
  ) {
    throw new Error("invalid-batch-selection");
  }

  const response = await fetchImplementation(
    `${API_BASE_URL}/papers/batch-analysis`,
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
    throw new Error("batch-analysis-request-failed");
  }

  const data: unknown = await response.json();
  if (!isBatchAnalysisResponse(data, uniquePaperIds)) {
    throw new Error("invalid-batch-analysis-response");
  }

  return data;
}

function listUniquePaperIds(paperIds: string[]): string[] {
  return [...new Set(paperIds)];
}
