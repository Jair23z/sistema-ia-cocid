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
const { isChunkedDocument, preparePdfDocument } = require(
  "../.test-build/ui/lib/document-chunking.js",
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
    character_count: 10_000,
    word_count: 900,
    pages: [
      {
        page_number: 1,
        text: "First extracted page",
        character_count: 5_000,
        word_count: 450,
      },
      {
        page_number: 2,
        text: "Second extracted page",
        character_count: 5_000,
        word_count: 450,
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
    total_word_count: 900,
    chunks: [
      {
        document_id: DOCUMENT_ID,
        chunk_index: 1,
        page_start: 1,
        page_end: 1,
        text: "First chunk",
        character_count: 1_000,
        word_count: 500,
        text_hash: "a".repeat(64),
      },
      {
        document_id: DOCUMENT_ID,
        chunk_index: 2,
        page_start: 1,
        page_end: 2,
        text: "Second chunk",
        character_count: 950,
        word_count: 475,
        text_hash: "b".repeat(64),
      },
    ],
    requires_ocr: false,
    status: "chunked",
  };
}

function insufficientResponse() {
  return {
    document_id: DOCUMENT_ID,
    chunk_count: 0,
    total_word_count: 10,
    chunks: [],
    requires_ocr: true,
    status: "insufficient_text",
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

async function renderExtractedDocument(fetchMock) {
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
      .findByType("form")
      .props.onSubmit({ preventDefault: () => undefined });
    await Promise.resolve();
  });
  await act(async () => {
    findButton(renderer.root, /Procesar documento/).props.onClick();
    await Promise.resolve();
  });
  return renderer;
}

test("chunking client sends one POST and validates its exact contract", async () => {
  const calls = [];
  const payload = chunkResponse();
  const result = await preparePdfDocument(DOCUMENT_ID, async (...parameters) => {
    calls.push(parameters);
    return { ok: true, json: async () => payload };
  });

  assert.equal(calls.length, 1);
  const [url, options] = calls[0];
  assert.match(url, new RegExp(`/documents/${DOCUMENT_ID}/chunks$`));
  assert.equal(options.method, "POST");
  assert.equal(options.headers.Accept, "application/json");
  assert.deepEqual(result, payload);
  assert.equal(isChunkedDocument({ ...payload, path: "private" }), false);
  assert.equal(isChunkedDocument({ ...payload, chunk_count: 1 }), false);
});

test("preparation UI shows loading, blocks duplicate submit and renders metrics", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const calls = [];
  let resolveChunking;
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
    return new Promise((resolve) => {
      resolveChunking = resolve;
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

  renderer = await renderExtractedDocument(fetchMock);
  const prepareButton = findButton(renderer.root, /Preparar documento/);
  assert.equal(prepareButton.props.disabled, false);

  await act(async () => {
    prepareButton.props.onClick();
    prepareButton.props.onClick();
    await Promise.resolve();
  });

  assert.equal(calls.length, 3);
  assertVisibleText(renderer.root, "Preparando documento...");
  assert.equal(
    findButton(renderer.root, /Preparando documento/).props.disabled,
    true,
  );

  await act(async () => {
    resolveChunking({ ok: true, json: async () => chunkResponse() });
    await Promise.resolve();
  });

  assertVisibleText(renderer.root, "Documento preparado correctamente");
  assertVisibleText(renderer.root, "Fragmentos2");
  assertVisibleText(renderer.root, "Total de palabras900");
  assertVisibleText(renderer.root, "Promedio por fragmento488 palabras");
  assertVisibleText(renderer.root, "EstadoPreparado");
  assert.equal(calls.length, 3);
});

test("preparation UI explains insufficient extracted text", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const file = validPdfFile();
  const fetchMock = async (url) => {
    const requestUrl = String(url);
    if (requestUrl.endsWith("/documents/upload")) {
      return { ok: true, json: async () => uploadResponse(file) };
    }
    if (requestUrl.endsWith("/extract")) {
      return { ok: true, json: async () => extractionResponse() };
    }
    return { ok: true, json: async () => insufficientResponse() };
  };

  let renderer;
  t.after(async () => {
    if (renderer) {
      await act(async () => renderer.unmount());
    }
    globalThis.fetch = originalFetch;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  });

  renderer = await renderExtractedDocument(fetchMock);
  await act(async () => {
    findButton(renderer.root, /Preparar documento/).props.onClick();
    await Promise.resolve();
  });

  assertVisibleText(renderer.root, "No existe suficiente texto extraído");
  assertVisibleText(renderer.root, "Fragmentos0");
  assertVisibleText(renderer.root, "EstadoTexto insuficiente");
});

test("preparation UI shows a friendly error and permits retry", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const originalConsoleError = console.error;
  const file = validPdfFile();
  const fetchMock = async (url) => {
    const requestUrl = String(url);
    if (requestUrl.endsWith("/documents/upload")) {
      return { ok: true, json: async () => uploadResponse(file) };
    }
    if (requestUrl.endsWith("/extract")) {
      return { ok: true, json: async () => extractionResponse() };
    }
    return { ok: false, status: 500 };
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

  renderer = await renderExtractedDocument(fetchMock);
  await act(async () => {
    findButton(renderer.root, /Preparar documento/).props.onClick();
    await Promise.resolve();
  });

  assertVisibleText(renderer.root, "No fue posible preparar el documento");
  assert.equal(findButton(renderer.root, /Preparar documento/).props.disabled, false);
});
