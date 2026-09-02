import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import TestRenderer from "react-test-renderer";
import { renderToString } from "react-dom/server";

const require = createRequire(import.meta.url);
const Module = require("node:module");
const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const compiledAppDirectory = path.resolve(testDirectory, "../.test-build/ui");
const originalResolveFilename = Module._resolveFilename;

Module._resolveFilename = function resolveTestAlias(
  request,
  parent,
  isMain,
  options,
) {
  if (request.startsWith("@/app/")) {
    const relativeModule = request.slice("@/app/".length);
    return path.join(compiledAppDirectory, `${relativeModule}.js`);
  }

  return originalResolveFilename.call(this, request, parent, isMain, options);
};

const Home = require("../.test-build/ui/page.js").default;
const { BatchComparisonResults } = require(
  "../.test-build/ui/components/batch-comparison-results.js",
);
Module._resolveFilename = originalResolveFilename;

const { act, create } = TestRenderer;
const React = require("react");

function createPaper(index) {
  return {
    id: `https://openalex.org/W${index}`,
    title: `Publicación científica ${index}`,
    authors: [`Autora ${index}`],
    year: 2020 + index,
    publication_date: `202${index}-01-01`,
    source: `Revista ${index}`,
    publication_type: "article",
    doi: `https://doi.org/10.1000/${index}`,
    citations: index * 10,
    openalex_id: `W${index}`,
    openalex_url: `https://openalex.org/W${index}`,
    publication_url: `https://example.org/paper-${index}`,
    is_open_access: true,
    open_access_status: "gold",
    abstract: `Resumen de la publicación científica ${index}.`,
  };
}

function createStoredSearch() {
  return JSON.stringify({
    query: "inteligencia artificial",
    fromYear: "",
    toYear: "",
    publicationType: "",
    openAccess: "",
    papers: Array.from({ length: 6 }, (_, index) => createPaper(index + 1)),
  });
}

function scientificAnalysis(label) {
  return {
    objective: `Objetivo ${label}`,
    methodology: `Metodología ${label}`,
    results: `Resultados ${label}`,
    conclusions: `Conclusiones ${label}`,
    findings: [`Hallazgo ${label}`],
  };
}

function comparisonPoint(text) {
  return {
    text,
    supporting_papers: ["W1", "W2"],
  };
}

function batchComparisonResponse() {
  return {
    batch_analysis: {
      requested_count: 3,
      processed_count: 3,
      success_count: 2,
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
          status: "success",
          analysis: scientificAnalysis("W2"),
          error: null,
        },
        {
          openalex_id: "W3",
          status: "error",
          analysis: null,
          error: {
            code: "paper_not_found",
            message: "La publicación no fue encontrada en OpenAlex.",
          },
        },
      ],
    },
    comparison_status: "completed",
    considered_count: 2,
    considered_papers: [
      {
        openalex_id: "W1",
        title: "Publicación científica 1",
        doi: "https://doi.org/10.1000/1",
        year: 2021,
        source: "Revista 1",
      },
      {
        openalex_id: "W2",
        title: "Publicación científica 2",
        doi: null,
        year: 2022,
        source: "Revista 2",
      },
    ],
    excluded_papers: [
      {
        openalex_id: "W3",
        reason: "analysis_error",
        message: "La publicación no fue encontrada en OpenAlex.",
        error_code: "paper_not_found",
      },
    ],
    comparison: {
      summary: "Resumen comparativo de W1 y W2.",
      common_points: [comparisonPoint("Coincidencia sustentada.")],
      differences: [comparisonPoint("Diferencia sustentada.")],
      trends: [comparisonPoint("Tendencia sustentada.")],
      research_gaps: [
        comparisonPoint(
          "Entre las publicaciones analizadas se observa poca evidencia longitudinal.",
        ),
      ],
    },
  };
}

function insufficientComparisonResponse() {
  return {
    batch_analysis: {
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
    },
    comparison_status: "insufficient_comparable_papers",
    considered_count: 1,
    considered_papers: [
      {
        openalex_id: "W1",
        title: "Publicación científica 1",
        doi: null,
        year: 2021,
        source: "Revista 1",
      },
    ],
    excluded_papers: [
      {
        openalex_id: "W2",
        reason: "analysis_error",
        message: "La publicación no fue encontrada en OpenAlex.",
        error_code: "paper_not_found",
      },
    ],
    comparison: null,
  };
}

function fivePaperComparisonResponse() {
  const ids = ["W1", "W2", "W3", "W4", "W5"];
  return {
    batch_analysis: {
      requested_count: 5,
      processed_count: 5,
      success_count: 5,
      error_count: 0,
      results: ids.map((openalexId) => ({
        openalex_id: openalexId,
        status: "success",
        analysis: scientificAnalysis(openalexId),
        error: null,
      })),
    },
    comparison_status: "completed",
    considered_count: 5,
    considered_papers: ids.map((openalexId, index) => ({
      openalex_id: openalexId,
      title: `Publicación científica ${index + 1}`,
      doi: null,
      year: 2021 + index,
      source: `Revista ${index + 1}`,
    })),
    excluded_papers: [],
    comparison: {
      summary: "Resumen comparativo de cinco publicaciones.",
      common_points: [comparisonPoint("Coincidencia de la muestra.")],
      differences: [comparisonPoint("Diferencia de la muestra.")],
      trends: [comparisonPoint("Tendencia de la muestra.")],
      research_gaps: [
        comparisonPoint(
          "Esta muestra presenta poca evidencia sobre seguimiento longitudinal.",
        ),
      ],
    },
  };
}

function nodeText(node) {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }

  if (!node || !Array.isArray(node.children)) {
    return "";
  }

  return node.children.map(nodeText).join("");
}

function findCompareButton(root) {
  return root.find(
    (node) =>
      node.type === "button" &&
      /Comparar publicaciones|Comparando publicaciones/.test(nodeText(node)),
  );
}

function findClearFiltersButton(root) {
  return root.find(
    (node) =>
      node.type === "button" && nodeText(node) === "Limpiar filtros",
  );
}

function findCheckboxes(root) {
  return root.findAll(
    (node) => node.type === "input" && node.props.type === "checkbox",
  );
}

function assertVisibleText(root, expectedText) {
  assert.ok(
    root.findAll((node) => nodeText(node).includes(expectedText)).length > 0,
    `No se encontró el texto visible: ${expectedText}`,
  );
}

test("SSR and the first client render use the same filter-button state", () => {
  const serverMarkup = renderToString(React.createElement(Home));
  const clearFiltersButton = serverMarkup.match(
    /<button[^>]*>Limpiar filtros<\/button>/,
  );

  assert.ok(clearFiltersButton, "SSR debe incluir el botón Limpiar filtros");
  assert.doesNotMatch(clearFiltersButton[0], /\sdisabled(?:=|\s|>)/);
});

test("the real results interface completes the mocked comparison flow", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;

  const originalFetch = globalThis.fetch;
  const originalSelf = globalThis.self;
  const originalSessionStorage = globalThis.sessionStorage;
  const originalWindow = globalThis.window;
  const fetchCalls = [];
  let resolveRequest;

  globalThis.sessionStorage = {
    getItem: () => createStoredSearch(),
    removeItem: () => undefined,
    setItem: () => undefined,
  };
  globalThis.window = {
    clearTimeout,
    setTimeout,
  };
  globalThis.self = globalThis.window;
  globalThis.fetch = (...parameters) => {
    fetchCalls.push(parameters);
    return new Promise((resolve) => {
      resolveRequest = resolve;
    });
  };

  let renderer;
  t.after(async () => {
    if (renderer) {
      await act(async () => renderer.unmount());
    }
    globalThis.fetch = originalFetch;
    globalThis.self = originalSelf;
    globalThis.sessionStorage = originalSessionStorage;
    globalThis.window = originalWindow;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  });

  await act(async () => {
    renderer = create(React.createElement(Home));
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 5));
  });

  let checkboxes = findCheckboxes(renderer.root);
  assert.equal(checkboxes.length, 6);
  assert.equal(findClearFiltersButton(renderer.root).props.disabled, true);
  assert.equal(findCompareButton(renderer.root).props.disabled, true);
  assertVisibleText(renderer.root, "0 publicaciones seleccionadas");

  await act(async () => checkboxes[0].props.onChange());
  assertVisibleText(renderer.root, "1 publicación seleccionada");
  assert.equal(findCompareButton(renderer.root).props.disabled, true);

  checkboxes = findCheckboxes(renderer.root);
  await act(async () => checkboxes[1].props.onChange());
  assertVisibleText(renderer.root, "2 publicaciones seleccionadas");
  assert.equal(findCompareButton(renderer.root).props.disabled, false);

  for (const checkboxIndex of [2, 3, 4]) {
    checkboxes = findCheckboxes(renderer.root);
    await act(async () => checkboxes[checkboxIndex].props.onChange());
  }

  checkboxes = findCheckboxes(renderer.root);
  assertVisibleText(renderer.root, "5 publicaciones seleccionadas");
  assert.equal(checkboxes[5].props.disabled, true);

  await act(async () => checkboxes[4].props.onChange());
  checkboxes = findCheckboxes(renderer.root);
  assertVisibleText(renderer.root, "4 publicaciones seleccionadas");
  assert.equal(checkboxes[5].props.disabled, false);

  checkboxes = findCheckboxes(renderer.root);
  await act(async () => checkboxes[3].props.onChange());
  assertVisibleText(renderer.root, "3 publicaciones seleccionadas");

  const compareButton = findCompareButton(renderer.root);
  await act(async () => {
    compareButton.props.onClick();
    compareButton.props.onClick();
    await Promise.resolve();
  });

  assert.equal(fetchCalls.length, 1);
  assert.equal(
    fetchCalls[0][0],
    "http://127.0.0.1:8000/papers/batch-comparison",
  );
  assert.deepEqual(JSON.parse(fetchCalls[0][1].body), {
    paper_ids: ["W1", "W2", "W3"],
  });
  assert.equal(findCompareButton(renderer.root).props.disabled, true);
  assertVisibleText(renderer.root, "Comparando publicaciones...");
  assert.ok(findCheckboxes(renderer.root).every((checkbox) => checkbox.props.disabled));

  await act(async () => {
    resolveRequest({
      ok: true,
      json: async () => batchComparisonResponse(),
    });
    await Promise.resolve();
  });

  assertVisibleText(renderer.root, "Resumen comparativo de W1 y W2.");
  assertVisibleText(renderer.root, "Objetivo W1");
  assertVisibleText(renderer.root, "Metodología W2");
  assertVisibleText(renderer.root, "Coincidencia sustentada.");
  assertVisibleText(renderer.root, "Diferencia sustentada.");
  assertVisibleText(renderer.root, "Tendencia sustentada.");
  assertVisibleText(renderer.root, "P1");
  assertVisibleText(renderer.root, "P2");
  assertVisibleText(
    renderer.root,
    "La publicación no fue encontrada en OpenAlex.",
  );
  assertVisibleText(
    renderer.root,
    "Las brechas identificadas corresponden únicamente al conjunto",
  );
  const responsiveTables = renderer.root.findAll(
    (node) => node.props["data-responsive-table"] === "horizontal-scroll",
  );
  assert.equal(responsiveTables.length, 1);
  assert.match(responsiveTables[0].props.className, /overflow-x-auto/);
  assert.equal(fetchCalls.length, 1);
});

test("the comparison view explains insufficient comparable papers", async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalSelf = globalThis.self;
  const originalWindow = globalThis.window;
  globalThis.window = { clearTimeout, setTimeout };
  globalThis.self = globalThis.window;
  let renderer;

  try {
    await act(async () => {
      renderer = create(
        React.createElement(BatchComparisonResults, {
          response: insufficientComparisonResponse(),
          papers: [createPaper(1), createPaper(2)],
        }),
      );
    });

    assertVisibleText(
      renderer.root,
      "No existen suficientes publicaciones con información",
    );
    assertVisibleText(renderer.root, "Publicaciones consideradas (1)");
    assertVisibleText(renderer.root, "Publicaciones excluidas (1)");
    assertVisibleText(
      renderer.root,
      "La publicación no fue encontrada en OpenAlex.",
    );
  } finally {
    if (renderer) {
      await act(async () => renderer.unmount());
    }
    globalThis.self = originalSelf;
    globalThis.window = originalWindow;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  }
});

test("the matrix renders four fields across five paper columns", async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalSelf = globalThis.self;
  const originalWindow = globalThis.window;
  globalThis.window = { clearTimeout, setTimeout };
  globalThis.self = globalThis.window;
  let renderer;

  try {
    await act(async () => {
      renderer = create(
        React.createElement(BatchComparisonResults, {
          response: fivePaperComparisonResponse(),
          papers: Array.from({ length: 5 }, (_, index) =>
            createPaper(index + 1),
          ),
        }),
      );
    });

    const table = renderer.root.findByType("table");
    const columnHeaders = table.findAll(
      (node) => node.type === "th" && node.props.scope === "col",
    );
    const rowHeaders = table.findAll(
      (node) => node.type === "th" && node.props.scope === "row",
    );
    const cells = table.findAll((node) => node.type === "td");

    assert.equal(columnHeaders.length, 6);
    assert.equal(rowHeaders.length, 4);
    assert.equal(cells.length, 20);
    assertVisibleText(renderer.root, "Conclusiones W5");
  } finally {
    if (renderer) {
      await act(async () => renderer.unmount());
    }
    globalThis.self = originalSelf;
    globalThis.window = originalWindow;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  }
});

test("the real results interface shows a friendly general error and permits retry", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;

  const originalFetch = globalThis.fetch;
  const originalSelf = globalThis.self;
  const originalSessionStorage = globalThis.sessionStorage;
  const originalWindow = globalThis.window;
  const originalConsoleError = console.error;
  let callCount = 0;

  globalThis.sessionStorage = {
    getItem: () => createStoredSearch(),
    removeItem: () => undefined,
    setItem: () => undefined,
  };
  globalThis.window = { clearTimeout, setTimeout };
  globalThis.self = globalThis.window;
  console.error = () => undefined;
  globalThis.fetch = async () => {
    callCount += 1;
    return { ok: false, status: 502 };
  };

  let renderer;
  t.after(async () => {
    if (renderer) {
      await act(async () => renderer.unmount());
    }
    globalThis.fetch = originalFetch;
    globalThis.self = originalSelf;
    globalThis.sessionStorage = originalSessionStorage;
    globalThis.window = originalWindow;
    console.error = originalConsoleError;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  });

  await act(async () => {
    renderer = create(React.createElement(Home));
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 5));
  });

  let checkboxes = findCheckboxes(renderer.root);
  await act(async () => checkboxes[0].props.onChange());
  checkboxes = findCheckboxes(renderer.root);
  await act(async () => checkboxes[1].props.onChange());

  await act(async () => {
    findCompareButton(renderer.root).props.onClick();
    await Promise.resolve();
  });

  assertVisibleText(
    renderer.root,
    "No fue posible comparar las publicaciones seleccionadas.",
  );
  assert.equal(findCompareButton(renderer.root).props.disabled, false);
  assert.equal(callCount, 1);

  await act(async () => {
    findCompareButton(renderer.root).props.onClick();
    await Promise.resolve();
  });
  assert.equal(callCount, 2);
});
