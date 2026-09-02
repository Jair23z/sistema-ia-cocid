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
const { extractPdfDocument, isExtractedDocument } = require(
  "../.test-build/ui/lib/document-extraction.js",
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

function extractionResponse({ requiresOcr = false } = {}) {
  return {
    document_id: DOCUMENT_ID,
    page_count: 2,
    character_count: 25,
    word_count: 4,
    pages: [
      {
        page_number: 1,
        text: "Scientific evidence",
        character_count: 19,
        word_count: 2,
      },
      {
        page_number: 2,
        text: "Page 2",
        character_count: 6,
        word_count: 2,
      },
    ],
    requires_ocr: requiresOcr,
    status: "extracted",
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

async function renderUploadedDocument(fetchMock) {
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
  return { renderer, file };
}

test("extraction client sends one POST and validates the complete contract", async () => {
  const calls = [];
  const responsePayload = extractionResponse();
  const response = await extractPdfDocument(DOCUMENT_ID, async (...parameters) => {
    calls.push(parameters);
    return { ok: true, json: async () => responsePayload };
  });

  assert.equal(calls.length, 1);
  const [url, options] = calls[0];
  assert.match(url, new RegExp(`/documents/${DOCUMENT_ID}/extract$`));
  assert.equal(options.method, "POST");
  assert.equal(options.headers.Accept, "application/json");
  assert.deepEqual(response, responsePayload);
  assert.equal(isExtractedDocument({ ...responsePayload, path: "private" }), false);
  assert.equal(
    isExtractedDocument({ ...responsePayload, character_count: 999 }),
    false,
  );
});

test("processing UI shows loading, blocks duplicate submit and renders metadata", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const calls = [];
  let resolveExtraction;
  const file = validPdfFile();
  const fetchMock = (...parameters) => {
    calls.push(parameters);
    if (String(parameters[0]).endsWith("/documents/upload")) {
      return Promise.resolve({ ok: true, json: async () => uploadResponse(file) });
    }
    return new Promise((resolve) => {
      resolveExtraction = resolve;
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

  ({ renderer } = await renderUploadedDocument(fetchMock));
  const processButton = findButton(renderer.root, /Procesar documento/);
  assert.equal(processButton.props.disabled, false);

  await act(async () => {
    processButton.props.onClick();
    processButton.props.onClick();
    await Promise.resolve();
  });

  assert.equal(calls.length, 2);
  assertVisibleText(renderer.root, "Procesando documento...");
  assert.equal(
    findButton(renderer.root, /Procesando documento/).props.disabled,
    true,
  );

  await act(async () => {
    resolveExtraction({ ok: true, json: async () => extractionResponse() });
    await Promise.resolve();
  });

  assertVisibleText(renderer.root, "Documento procesado correctamente");
  assertVisibleText(renderer.root, "Páginas2");
  assertVisibleText(renderer.root, "Palabras4");
  assertVisibleText(renderer.root, "Caracteres25");
  assertVisibleText(renderer.root, "EstadoExtraído");
  assert.equal(calls.length, 2);
});

test("processing UI renders the OCR warning", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const file = validPdfFile();
  const fetchMock = async (url) =>
    String(url).endsWith("/documents/upload")
      ? { ok: true, json: async () => uploadResponse(file) }
      : { ok: true, json: async () => extractionResponse({ requiresOcr: true }) };

  let renderer;
  t.after(async () => {
    if (renderer) {
      await act(async () => renderer.unmount());
    }
    globalThis.fetch = originalFetch;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  });

  ({ renderer } = await renderUploadedDocument(fetchMock));
  await act(async () => {
    findButton(renderer.root, /Procesar documento/).props.onClick();
    await Promise.resolve();
  });

  assertVisibleText(renderer.root, "probablemente requiere");
  assertVisibleText(renderer.root, "no se ejecutó OCR");
});

test("processing UI shows a friendly error and allows retry", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const originalConsoleError = console.error;
  const file = validPdfFile();
  globalThis.fetch = async (url) =>
    String(url).endsWith("/documents/upload")
      ? { ok: true, json: async () => uploadResponse(file) }
      : { ok: false, status: 422 };
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

  ({ renderer } = await renderUploadedDocument(globalThis.fetch));
  await act(async () => {
    findButton(renderer.root, /Procesar documento/).props.onClick();
    await Promise.resolve();
  });

  assertVisibleText(renderer.root, "No fue posible procesar el documento");
  assert.equal(findButton(renderer.root, /Procesar documento/).props.disabled, false);
});
