import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const {
  isBatchComparisonResponse,
  requestBatchComparison,
} = require("../.test-build/ui/lib/batch-comparison.js");

function scientificAnalysis(label) {
  return {
    objective: `Objetivo ${label}`,
    methodology: `Metodología ${label}`,
    results: `Resultados ${label}`,
    conclusions: `Conclusiones ${label}`,
    findings: [`Hallazgo ${label}`],
  };
}

function comparativePoint(ids, text = "Observación comparativa sustentada.") {
  return { text, supporting_papers: ids };
}

function comparisonResponse(count) {
  const ids = Array.from({ length: count }, (_, index) => `W${index + 1}`);
  return {
    batch_analysis: {
      requested_count: count,
      processed_count: count,
      success_count: count,
      error_count: 0,
      results: ids.map((openalexId) => ({
        openalex_id: openalexId,
        status: "success",
        analysis: scientificAnalysis(openalexId),
        error: null,
      })),
    },
    comparison_status: "completed",
    considered_count: count,
    considered_papers: ids.map((openalexId, index) => ({
      openalex_id: openalexId,
      title: `Publicación ${index + 1}`,
      doi: index === 0 ? null : `https://doi.org/10.1000/${index + 1}`,
      year: 2020 + index,
      source: `Revista ${index + 1}`,
    })),
    excluded_papers: [],
    comparison: {
      summary: "Resumen limitado al conjunto analizado.",
      common_points: [comparativePoint(ids.slice(0, 2))],
      differences: [comparativePoint(ids.slice(0, 2))],
      trends: [comparativePoint(ids.slice(0, 2))],
      research_gaps: [
        comparativePoint(
          [ids[0]],
          "En el conjunto seleccionado se observa poca evidencia longitudinal.",
        ),
      ],
    },
  };
}

test("comparison contract accepts completed responses for two and five papers", () => {
  for (const count of [2, 5]) {
    const response = comparisonResponse(count);
    const expectedIds = response.considered_papers.map(
      (paper) => paper.openalex_id,
    );

    assert.equal(isBatchComparisonResponse(response, expectedIds), true);
  }
});

test("comparison request sends exactly one POST with selected paper IDs", async () => {
  const calls = [];
  const fetchMock = async (...parameters) => {
    calls.push(parameters);
    return {
      ok: true,
      json: async () => comparisonResponse(2),
    };
  };

  const response = await requestBatchComparison(["W1", "W2"], fetchMock);

  assert.equal(calls.length, 1);
  const [url, options] = calls[0];
  assert.match(url, /\/papers\/batch-comparison$/);
  assert.equal(options.method, "POST");
  assert.deepEqual(JSON.parse(options.body), { paper_ids: ["W1", "W2"] });
  assert.equal(response.comparison_status, "completed");
});

test("invalid comparison selection is rejected before fetch", async () => {
  let callCount = 0;
  const fetchMock = async () => {
    callCount += 1;
  };

  await assert.rejects(
    requestBatchComparison(["W1"], fetchMock),
    /invalid-batch-comparison-selection/,
  );
  await assert.rejects(
    requestBatchComparison(["W1", "W1"], fetchMock),
    /invalid-batch-comparison-selection/,
  );
  await assert.rejects(
    requestBatchComparison(
      ["W1", "W2", "W3", "W4", "W5", "W6"],
      fetchMock,
    ),
    /invalid-batch-comparison-selection/,
  );
  assert.equal(callCount, 0);
});

test("comparison guard rejects invalid references and unscoped gaps", () => {
  const unknownReference = comparisonResponse(2);
  unknownReference.comparison.common_points[0].supporting_papers = [
    "W1",
    "W999",
  ];
  assert.equal(isBatchComparisonResponse(unknownReference), false);

  const duplicateReference = comparisonResponse(2);
  duplicateReference.comparison.trends[0].supporting_papers = ["W1", "W1"];
  assert.equal(isBatchComparisonResponse(duplicateReference), false);

  const unscopedGap = comparisonResponse(2);
  unscopedGap.comparison.research_gaps[0].text =
    "No existen investigaciones sobre esta variable.";
  assert.equal(isBatchComparisonResponse(unscopedGap), false);
});

test("comparison guard accepts the insufficient state with exclusions", () => {
  const response = comparisonResponse(2);
  const failedResult = {
    openalex_id: "W2",
    status: "error",
    analysis: null,
    error: {
      code: "paper_not_found",
      message: "La publicación no fue encontrada.",
    },
  };
  response.batch_analysis.results[1] = failedResult;
  response.batch_analysis.success_count = 1;
  response.batch_analysis.error_count = 1;
  response.comparison_status = "insufficient_comparable_papers";
  response.considered_count = 1;
  response.considered_papers = response.considered_papers.slice(0, 1);
  response.excluded_papers = [
    {
      openalex_id: "W2",
      reason: "analysis_error",
      message: "La publicación no fue encontrada.",
      error_code: "paper_not_found",
    },
  ];
  response.comparison = null;

  assert.equal(isBatchComparisonResponse(response, ["W1", "W2"]), true);
});
