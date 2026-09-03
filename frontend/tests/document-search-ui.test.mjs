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

const { DocumentUpload } = require(
  "../.test-build/ui/components/document-upload.js",
);
const { isSemanticSearchResponse, searchPdfDocument } = require(
  "../.test-build/ui/lib/document-search.js",
);
Module._resolveFilename = originalResolveFilename;

const { act, create } = TestRenderer;
const React = require("react");
const DOCUMENT_ID = "4beed958-5bf3-4e02-9c57-df9f2b547806";

function validPdfFile() {
  return new File(["%PDF-1.4\n%%EOF\n"], "artículo.pdf", {
    type: "application/pdf",
  });
}

function uploadResponse(file) {
  return {
    document_id: DOCUMENT_ID,
    filename: file.name,
    size_bytes: file.size,
    status: "uploaded",
  };
}

function extractionResponse() {
  return {
    document_id: DOCUMENT_ID,
    page_count: 2,
    character_count: 44,
    word_count: 6,
    pages: [
      {
        page_number: 1,
        text: "A methodology with interviews",
        character_count: 29,
        word_count: 4,
      },
      {
        page_number: 2,
        text: "Other evidence.",
        character_count: 15,
        word_count: 2,
      },
    ],
    requires_ocr: false,
    status: "extracted",
  };
}

function chunkResponse() {
  return {
    document_id: DOCUMENT_ID,
    chunk_count: 2,
    total_word_count: 6,
    chunks: [
      {
        document_id: DOCUMENT_ID,
        chunk_index: 1,
        page_start: 1,
        page_end: 1,
        text: "A methodology with interviews",
        character_count: 29,
        word_count: 4,
        text_hash: "a".repeat(64),
      },
      {
        document_id: DOCUMENT_ID,
        chunk_index: 2,
        page_start: 1,
        page_end: 2,
        text: "Other evidence.",
        character_count: 15,
        word_count: 2,
        text_hash: "b".repeat(64),
      },
    ],
    requires_ocr: false,
    status: "chunked",
  };
}

function searchResponse() {
  return {
    document_id: DOCUMENT_ID,
    query: "¿Qué metodología utilizó el estudio?",
    result_count: 2,
    results: [
      {
        document_id: DOCUMENT_ID,
        chunk_index: 1,
        page_start: 1,
        page_end: 1,
        text: "A methodology with interviews",
        score: 0.87321,
      },
      {
        document_id: DOCUMENT_ID,
        chunk_index: 2,
        page_start: 1,
        page_end: 2,
        text: "Other evidence.",
        score: 0.41234,
      },
    ],
    status: "completed",
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

function assertVisibleText(root, expectedText) {
  assert.ok(
    root.findAll((node) => nodeText(node).includes(expectedText)).length > 0,
    `No se encontró el texto visible: ${expectedText}`,
  );
}

function findButton(root, labelPattern) {
  return root.find(
    (node) => node.type === "button" && labelPattern.test(nodeText(node)),
  );
}

async function renderPreparedDocument(fetchMock) {
  globalThis.fetch = fetchMock;
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(DocumentUpload));
  });

  const file = validPdfFile();
  const fileInput = renderer.root.find(
    (node) => node.type === "input" && node.props.type === "file",
  );
  await act(async () => fileInput.props.onChange({ target: { files: [file] } }));
  await act(async () => {
    renderer.root
      .findAllByType("form")[0]
      .props.onSubmit({ preventDefault: () => undefined });
    await Promise.resolve();
  });
  await act(async () => {
    findButton(renderer.root, /Procesar documento/).props.onClick();
    await Promise.resolve();
  });
  await act(async () => {
    findButton(renderer.root, /Preparar documento/).props.onClick();
    await Promise.resolve();
  });
  return renderer;
}

test("semantic-search client sends the exact public contract", async () => {
  const calls = [];
  const payload = searchResponse();
  const result = await searchPdfDocument(
    DOCUMENT_ID,
    { query: "  ¿Qué metodología utilizó el estudio?  " },
    async (...parameters) => {
      calls.push(parameters);
      return { ok: true, json: async () => payload };
    },
  );

  assert.equal(calls.length, 1);
  const [url, options] = calls[0];
  assert.match(url, new RegExp(`/documents/${DOCUMENT_ID}/search$`));
  assert.equal(options.method, "POST");
  assert.equal(options.headers.Accept, "application/json");
  assert.equal(options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(options.body), {
    query: "¿Qué metodología utilizó el estudio?",
    top_k: 4,
  });
  assert.deepEqual(result, payload);
  assert.equal(
    isSemanticSearchResponse({
      ...payload,
      results: [{ ...payload.results[0], embedding: [1, 2] }],
      result_count: 1,
    }),
    false,
  );
});

test("search UI blocks duplicate submit and renders ordered traceable results", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const calls = [];
  let resolveSearch;
  const file = validPdfFile();
  const fetchMock = (...parameters) => {
    calls.push(parameters);
    const url = String(parameters[0]);
    if (url.endsWith("/documents/upload")) {
      return Promise.resolve({ ok: true, json: async () => uploadResponse(file) });
    }
    if (url.endsWith("/extract")) {
      return Promise.resolve({ ok: true, json: async () => extractionResponse() });
    }
    if (url.endsWith("/chunks")) {
      return Promise.resolve({ ok: true, json: async () => chunkResponse() });
    }
    return new Promise((resolve) => {
      resolveSearch = resolve;
    });
  };

  let renderer;
  t.after(async () => {
    if (renderer) {
      await act(async () => renderer.unmount());
    }
    globalThis.fetch = originalFetch;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  });

  renderer = await renderPreparedDocument(fetchMock);
  assertVisibleText(renderer.root, "Buscar dentro del documento");
  const queryInput = renderer.root.find(
    (node) =>
      node.type === "input" &&
      node.props.placeholder === "¿Qué metodología utilizó el estudio?",
  );
  assert.equal(findButton(renderer.root, /^Buscar en documento$/).props.disabled, true);

  await act(async () =>
    queryInput.props.onChange({
      target: { value: "¿Qué metodología utilizó el estudio?" },
    }),
  );
  const searchForm = renderer.root.find(
    (node) =>
      node.type === "form" &&
      node.props["aria-label"] === "Búsqueda dentro del documento",
  );
  await act(async () => {
    searchForm.props.onSubmit({ preventDefault: () => undefined });
    searchForm.props.onSubmit({ preventDefault: () => undefined });
    await Promise.resolve();
  });

  assert.equal(calls.length, 4);
  assertVisibleText(renderer.root, "Buscando en documento...");
  assertVisibleText(renderer.root, "Buscando fragmentos relevantes...");
  assert.equal(
    findButton(renderer.root, /Buscando en documento/).props.disabled,
    true,
  );

  await act(async () => {
    resolveSearch({ ok: true, json: async () => searchResponse() });
    await Promise.resolve();
  });

  assertVisibleText(renderer.root, "2 fragmentos recuperados");
  assertVisibleText(renderer.root, "Página 1");
  assertVisibleText(renderer.root, "Páginas 1–2");
  assertVisibleText(renderer.root, "Relevancia: 0.873");
  assertVisibleText(renderer.root, "Relevancia: 0.412");
  assert.equal(calls.length, 4);
});

test("search UI shows a friendly error and permits retry", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const originalConsoleError = console.error;
  const file = validPdfFile();
  globalThis.fetch = async (url) => {
    const requestUrl = String(url);
    if (requestUrl.endsWith("/documents/upload")) {
      return { ok: true, json: async () => uploadResponse(file) };
    }
    if (requestUrl.endsWith("/extract")) {
      return { ok: true, json: async () => extractionResponse() };
    }
    if (requestUrl.endsWith("/chunks")) {
      return { ok: true, json: async () => chunkResponse() };
    }
    return { ok: false, status: 503 };
  };
  console.error = () => undefined;

  let renderer;
  t.after(async () => {
    if (renderer) {
      await act(async () => renderer.unmount());
    }
    globalThis.fetch = originalFetch;
    console.error = originalConsoleError;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  });

  renderer = await renderPreparedDocument(globalThis.fetch);
  const queryInput = renderer.root.find(
    (node) => node.props.placeholder === "¿Qué metodología utilizó el estudio?",
  );
  await act(async () =>
    queryInput.props.onChange({ target: { value: "methodology" } }),
  );
  await act(async () => {
    const searchForm = renderer.root.find(
      (node) =>
        node.type === "form" &&
        node.props["aria-label"] === "Búsqueda dentro del documento",
    );
    searchForm.props.onSubmit({ preventDefault: () => undefined });
    await Promise.resolve();
  });

  assertVisibleText(renderer.root, "No fue posible buscar dentro del documento");
  assert.equal(findButton(renderer.root, /^Buscar en documento$/).props.disabled, false);
});
