import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const {
  MAX_BATCH_SELECTION,
  canAnalyzeSelection,
  claimBatchRequest,
  releaseBatchRequest,
  togglePaperSelection,
} = require("../.test-build/ui/lib/batch-selection.js");
const {
  isBatchAnalysisResponse,
  requestBatchScientificAnalysis,
} = require("../.test-build/ui/lib/batch-analysis.js");


function scientificAnalysis(label) {
  return {
    objective: `Objetivo ${label}`,
    methodology: `Metodología ${label}`,
    results: `Resultados ${label}`,
    conclusions: `Conclusiones ${label}`,
    findings: [`Hallazgo ${label}`],
  };
}

function validBatchResponse() {
  return {
    requested_count: 2,
    processed_count: 2,
    success_count: 1,
    error_count: 1,
    results: [
      {
        openalex_id: "W1",
        status: "success",
        analysis: scientificAnalysis("W1"),
        error: null,
      },
      {
        openalex_id: "W2",
        status: "error",
        analysis: null,
        error: {
          code: "paper_not_found",
          message: "La publicación no fue encontrada en OpenAlex.",
        },
      },
    ],
  };
}


test("batch action requires between two and five selected papers", () => {
  assert.equal(canAnalyzeSelection([]), false);
  assert.equal(canAnalyzeSelection(["W1"]), false);
  assert.equal(canAnalyzeSelection(["W1", "W1"]), false);
  assert.equal(canAnalyzeSelection(["W1", "invalid"]), false);
  assert.equal(canAnalyzeSelection(["W1", "W2"]), true);
  assert.equal(
    canAnalyzeSelection(["W1", "W2", "W3", "W4", "W5"]),
    true,
  );
  assert.equal(
    canAnalyzeSelection(["W1", "W2", "W3", "W4", "W5", "W6"]),
    false,
  );
});

test("selection blocks a sixth paper and still permits deselection", () => {
  let selected = [];
  for (let index = 1; index <= MAX_BATCH_SELECTION; index += 1) {
    selected = togglePaperSelection(selected, `W${index}`);
  }

  const blockedSelection = togglePaperSelection(selected, "W6");
  assert.deepEqual(blockedSelection, ["W1", "W2", "W3", "W4", "W5"]);

  const afterDeselection = togglePaperSelection(blockedSelection, "W3");
  assert.deepEqual(afterDeselection, ["W1", "W2", "W4", "W5"]);
});

test("selection stays unique and ignores invalid OpenAlex IDs", () => {
  const selectedOnce = togglePaperSelection([], "W123");
  const deselected = togglePaperSelection(selectedOnce, "W123");
  const invalidSelection = togglePaperSelection(deselected, "invalid-id");

  assert.deepEqual(selectedOnce, ["W123"]);
  assert.deepEqual(deselected, []);
  assert.deepEqual(invalidSelection, []);
});

test("request gate rejects a duplicate submit until released", () => {
  const requestGate = { current: false };

  assert.equal(claimBatchRequest(requestGate), true);
  assert.equal(claimBatchRequest(requestGate), false);
  assert.equal(requestGate.current, true);

  releaseBatchRequest(requestGate);
  assert.equal(requestGate.current, false);
  assert.equal(claimBatchRequest(requestGate), true);
});

test("batch request sends one POST with the frontend/backend contract", async () => {
  const calls = [];
  const fetchMock = async (...parameters) => {
    calls.push(parameters);
    return {
      ok: true,
      json: async () => validBatchResponse(),
    };
  };

  const response = await requestBatchScientificAnalysis(
    ["W1", "W2"],
    fetchMock,
  );

  assert.equal(calls.length, 1);
  const [url, options] = calls[0];
  assert.match(url, /\/papers\/batch-analysis$/);
  assert.equal(options.method, "POST");
  assert.equal(options.headers.Accept, "application/json");
  assert.equal(options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(options.body), { paper_ids: ["W1", "W2"] });
  assert.equal(response.success_count, 1);
  assert.equal(response.error_count, 1);
});

test("invalid selection is rejected before fetch", async () => {
  let callCount = 0;
  const fetchMock = async () => {
    callCount += 1;
  };

  await assert.rejects(
    requestBatchScientificAnalysis(["W1"], fetchMock),
    /invalid-batch-selection/,
  );
  await assert.rejects(
    requestBatchScientificAnalysis(
      ["W1", "W2", "W3", "W4", "W5", "W6"],
      fetchMock,
    ),
    /invalid-batch-selection/,
  );
  await assert.rejects(
    requestBatchScientificAnalysis(["W1", "W1"], fetchMock),
    /invalid-batch-selection/,
  );
  assert.equal(callCount, 0);
});

test("batch response guard rejects inconsistent counts and order", () => {
  const validResponse = validBatchResponse();
  assert.equal(isBatchAnalysisResponse(validResponse, ["W1", "W2"]), true);

  assert.equal(
    isBatchAnalysisResponse(
      { ...validResponse, success_count: 2 },
      ["W1", "W2"],
    ),
    false,
  );
  assert.equal(isBatchAnalysisResponse(validResponse, ["W2", "W1"]), false);
});
