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
const { askPdfDocument, isDocumentAnswerResponse } = require(
  "../.test-build/ui/lib/document-rag.js",
);
Module._resolveFilename = originalResolveFilename;

const { act, create } = TestRenderer;
const React = require("react");
const DOCUMENT_ID = "4beed958-5bf3-4e02-9c57-df9f2b547806";
const QUESTION = "¿Qué metodología utilizó el estudio?";
const INSUFFICIENT_ANSWER =
  "No existe evidencia suficiente en los fragmentos recuperados para responder esta pregunta.";

function validPdfFile() {
  return new File(["%PDF-1.4\n%%EOF\n"], "articulo.pdf", {
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
    page_count: 3,
    character_count: 49,
    word_count: 6,
    pages: [
      {
        page_number: 1,
        text: "Metodología del estudio.",
        character_count: 24,
        word_count: 3,
      },
      {
        page_number: 2,
        text: "Resultados del estudio.",
        character_count: 25,
        word_count: 3,
      },
      {
        page_number: 3,
        text: "",
        character_count: 0,
        word_count: 0,
      },
    ],
    requires_ocr: false,
    status: "extracted",
  };
}

function chunkResponse() {
  return {
    document_id: DOCUMENT_ID,
    chunk_count: 3,
    total_word_count: 6,
    chunks: [
      {
        document_id: DOCUMENT_ID,
        chunk_index: 1,
        page_start: 1,
        page_end: 1,
        text: "Primer fragmento.",
        character_count: 18,
        word_count: 2,
        text_hash: "a".repeat(64),
      },
      {
        document_id: DOCUMENT_ID,
        chunk_index: 2,
        page_start: 2,
        page_end: 3,
        text: "Segundo fragmento.",
        character_count: 19,
        word_count: 2,
        text_hash: "b".repeat(64),
      },
      {
        document_id: DOCUMENT_ID,
        chunk_index: 3,
        page_start: 2,
        page_end: 3,
        text: "Tercer fragmento.",
        character_count: 18,
        word_count: 2,
        text_hash: "c".repeat(64),
      },
    ],
    requires_ocr: false,
    status: "chunked",
  };
}

function answerResponse(evidenceStatus = "sufficient") {
  if (evidenceStatus === "insufficient") {
    return {
      document_id: DOCUMENT_ID,
      query: QUESTION,
      answer: INSUFFICIENT_ANSWER,
      evidence_status: "insufficient",
      citations: [],
      status: "completed",
    };
  }
  return {
    document_id: DOCUMENT_ID,
    query: QUESTION,
    answer:
      evidenceStatus === "partial"
        ? "Se identificaron entrevistas; el tamaño de muestra no puede determinarse."
        : "El estudio utilizó entrevistas semiestructuradas.",
    evidence_status: evidenceStatus,
    citations: [
      { chunk_index: 1, page_start: 1, page_end: 1 },
      { chunk_index: 2, page_start: 2, page_end: 3 },
      { chunk_index: 3, page_start: 2, page_end: 3 },
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

function visibleExactTextCount(root, expectedText) {
  return root.findAll(
    (node) =>
      (node.type === "li" || node.type === "p" || node.type === "span") &&
      nodeText(node) === expectedText,
  ).length;
}

function findButton(root, labelPattern) {
  return root.find(
    (node) => node.type === "button" && labelPattern.test(nodeText(node)),
  );
}

function baseFetch(file, answerHandler) {
  return (...parameters) => {
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
    if (url.endsWith("/ask")) {
      return answerHandler(...parameters);
    }
    throw new Error(`Unexpected request: ${url}`);
  };
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

function findQuestionForm(root) {
  return root.find(
    (node) =>
      node.type === "form" &&
      node.props["aria-label"] === "Pregunta sobre el documento",
  );
}

function findQuestionInput(root) {
  return root.find(
    (node) => node.type === "input" && node.props.id === "document-question",
  );
}

async function enterQuestion(renderer) {
  await act(async () =>
    findQuestionInput(renderer.root).props.onChange({
      target: { value: `  ${QUESTION}  ` },
    }),
  );
}

test("RAG client sends the exact contract and rejects internal fields", async () => {
  const calls = [];
  const payload = answerResponse("sufficient");
  const result = await askPdfDocument(
    DOCUMENT_ID,
    { query: `  ${QUESTION}  ` },
    async (...parameters) => {
      calls.push(parameters);
      return { ok: true, json: async () => payload };
    },
  );

  assert.equal(calls.length, 1);
  const [url, options] = calls[0];
  assert.match(url, new RegExp(`/documents/${DOCUMENT_ID}/ask$`));
  assert.equal(options.method, "POST");
  assert.deepEqual(JSON.parse(options.body), { query: QUESTION, top_k: 4 });
  assert.deepEqual(result, payload);
  assert.equal(isDocumentAnswerResponse({ ...payload, model: "hidden" }), false);
  assert.equal(
    isDocumentAnswerResponse({
      ...payload,
      citations: [payload.citations[0], payload.citations[0]],
    }),
    false,
  );
});

test("question UI shows loading, blocks duplicate submit, and renders sufficient evidence", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const calls = [];
  let resolveAnswer;
  const file = validPdfFile();
  const fetchMock = baseFetch(file, (...parameters) => {
    calls.push(parameters);
    return new Promise((resolve) => {
      resolveAnswer = resolve;
    });
  });
  let renderer;
  t.after(async () => {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  });

  renderer = await renderPreparedDocument(fetchMock);
  assertVisibleText(renderer.root, "Preguntar sobre el documento");
  assert.equal(findButton(renderer.root, /^Preguntar al documento$/).props.disabled, true);
  await enterQuestion(renderer);
  assert.equal(findButton(renderer.root, /^Preguntar al documento$/).props.disabled, false);

  await act(async () => {
    findQuestionForm(renderer.root).props.onSubmit({ preventDefault: () => undefined });
    findQuestionForm(renderer.root).props.onSubmit({ preventDefault: () => undefined });
    await Promise.resolve();
  });
  assert.equal(calls.length, 1);
  assertVisibleText(renderer.root, "Consultando documento...");
  assert.equal(findButton(renderer.root, /Consultando documento/).props.disabled, true);

  await act(async () => {
    resolveAnswer({ ok: true, json: async () => answerResponse("sufficient") });
    await Promise.resolve();
  });
  assertVisibleText(renderer.root, "Respuesta de IA");
  assertVisibleText(renderer.root, "Evidencia suficiente");
  assertVisibleText(renderer.root, "El estudio utilizó entrevistas semiestructuradas.");
  assert.equal(visibleExactTextCount(renderer.root, "Página 1"), 1);
  assert.equal(visibleExactTextCount(renderer.root, "Páginas 2–3"), 1);
  assert.equal(calls.length, 1);
});

test("question UI renders partial and visually deduplicates page ranges", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const file = validPdfFile();
  let renderer;
  t.after(async () => {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  });

  renderer = await renderPreparedDocument(
    baseFetch(file, async () => ({
      ok: true,
      json: async () => answerResponse("partial"),
    })),
  );
  await enterQuestion(renderer);
  await act(async () => {
    findQuestionForm(renderer.root).props.onSubmit({ preventDefault: () => undefined });
    await Promise.resolve();
  });
  assertVisibleText(renderer.root, "Evidencia parcial");
  assertVisibleText(renderer.root, "el tamaño de muestra no puede determinarse");
  assert.equal(visibleExactTextCount(renderer.root, "Páginas 2–3"), 1);
});

test("question UI renders insufficient evidence without sources", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const file = validPdfFile();
  let renderer;
  t.after(async () => {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  });

  renderer = await renderPreparedDocument(
    baseFetch(file, async () => ({
      ok: true,
      json: async () => answerResponse("insufficient"),
    })),
  );
  await enterQuestion(renderer);
  await act(async () => {
    findQuestionForm(renderer.root).props.onSubmit({ preventDefault: () => undefined });
    await Promise.resolve();
  });
  assertVisibleText(renderer.root, "Evidencia insuficiente");
  assertVisibleText(renderer.root, INSUFFICIENT_ANSWER);
  assert.equal(visibleExactTextCount(renderer.root, "Fuentes"), 0);
});

test("question UI shows a friendly error and permits retry", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const originalConsoleError = console.error;
  const file = validPdfFile();
  let askCount = 0;
  let renderer;
  console.error = () => undefined;
  t.after(async () => {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
    console.error = originalConsoleError;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  });

  renderer = await renderPreparedDocument(
    baseFetch(file, async () => {
      askCount += 1;
      return askCount === 1
        ? { ok: false, status: 503 }
        : { ok: true, json: async () => answerResponse("sufficient") };
    }),
  );
  await enterQuestion(renderer);
  await act(async () => {
    findQuestionForm(renderer.root).props.onSubmit({ preventDefault: () => undefined });
    await Promise.resolve();
  });
  assertVisibleText(renderer.root, "No fue posible responder la pregunta");
  assert.equal(findButton(renderer.root, /^Preguntar al documento$/).props.disabled, false);

  await act(async () => {
    findQuestionForm(renderer.root).props.onSubmit({ preventDefault: () => undefined });
    await Promise.resolve();
  });
  assert.equal(askCount, 2);
  assertVisibleText(renderer.root, "Evidencia suficiente");
});
