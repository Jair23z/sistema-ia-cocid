import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import TestRenderer from "react-test-renderer";

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

function batchResponse() {
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

function nodeText(node) {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }

  if (!node || !Array.isArray(node.children)) {
    return "";
  }

  return node.children.map(nodeText).join("");
}

function findAnalyzeButton(root) {
  return root.find(
    (node) =>
      node.type === "button" &&
      /Analizar seleccionados|Analizando seleccionados/.test(nodeText(node)),
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

test("the real results interface completes the mocked batch flow", async (t) => {
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
  assert.equal(findAnalyzeButton(renderer.root).props.disabled, true);
  assertVisibleText(renderer.root, "0 publicaciones seleccionadas");

  await act(async () => checkboxes[0].props.onChange());
  assertVisibleText(renderer.root, "1 publicación seleccionada");
  assert.equal(findAnalyzeButton(renderer.root).props.disabled, true);

  checkboxes = findCheckboxes(renderer.root);
  await act(async () => checkboxes[1].props.onChange());
  assertVisibleText(renderer.root, "2 publicaciones seleccionadas");
  assert.equal(findAnalyzeButton(renderer.root).props.disabled, false);

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

  for (const checkboxIndex of [2, 3]) {
    checkboxes = findCheckboxes(renderer.root);
    await act(async () => checkboxes[checkboxIndex].props.onChange());
  }
  assertVisibleText(renderer.root, "2 publicaciones seleccionadas");

  const analyzeButton = findAnalyzeButton(renderer.root);
  await act(async () => {
    analyzeButton.props.onClick();
    analyzeButton.props.onClick();
    await Promise.resolve();
  });

  assert.equal(fetchCalls.length, 1);
  assert.equal(
    fetchCalls[0][0],
    "http://127.0.0.1:8000/papers/batch-analysis",
  );
  assert.deepEqual(JSON.parse(fetchCalls[0][1].body), {
    paper_ids: ["W1", "W2"],
  });
  assert.equal(findAnalyzeButton(renderer.root).props.disabled, true);
  assertVisibleText(renderer.root, "Analizando 2 publicaciones...");
  assert.ok(findCheckboxes(renderer.root).every((checkbox) => checkbox.props.disabled));

  await act(async () => {
    resolveRequest({
      ok: true,
      json: async () => batchResponse(),
    });
    await Promise.resolve();
  });

  assertVisibleText(renderer.root, "Resultados individuales del lote");
  assertVisibleText(renderer.root, "Objetivo W1");
  assertVisibleText(
    renderer.root,
    "La publicación no fue encontrada en OpenAlex.",
  );
  assertVisibleText(renderer.root, "1 de 2 publicaciones procesadas correctamente");
  assert.equal(fetchCalls.length, 1);
});
