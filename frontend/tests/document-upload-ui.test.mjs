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
const {
  MAX_PDF_UPLOAD_BYTES,
  getPdfSelectionError,
  uploadPdfDocument,
} = require("../.test-build/ui/lib/document-upload.js");
Module._resolveFilename = originalResolveFilename;

const { act, create } = TestRenderer;
const React = require("react");
const VALID_DOCUMENT_ID = "4beed958-5bf3-4e02-9c57-df9f2b547806";

function validPdfFile() {
  return new File(["%PDF-1.4\n%%EOF\n"], "artículo científico.pdf", {
    type: "application/pdf",
  });
}

function uploadResponse(file) {
  return {
    document_id: VALID_DOCUMENT_ID,
    filename: file.name,
    size_bytes: file.size,
    status: "uploaded",
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

function findUploadButton(root) {
  return root.find(
    (node) =>
      node.type === "button" &&
      /Subir documento|Subiendo documento/.test(nodeText(node)),
  );
}

test("PDF selection validation rejects invalid client files", () => {
  assert.equal(getPdfSelectionError(validPdfFile()), null);
  assert.match(
    getPdfSelectionError(
      new File(["contenido"], "documento.txt", { type: "application/pdf" }),
    ),
    /extensión \.pdf/,
  );
  assert.match(
    getPdfSelectionError(
      new File(["contenido"], "documento.pdf", { type: "text/plain" }),
    ),
    /application\/pdf/,
  );
  assert.match(
    getPdfSelectionError(
      new File([], "documento.pdf", { type: "application/pdf" }),
    ),
    /vacío/,
  );
  assert.match(
    getPdfSelectionError({
      name: "documento.pdf",
      type: "application/pdf",
      size: MAX_PDF_UPLOAD_BYTES + 1,
    }),
    /15 MiB/,
  );
});

test("upload client sends multipart form data without overriding content type", async () => {
  const file = validPdfFile();
  const calls = [];
  const fetchMock = async (...parameters) => {
    calls.push(parameters);
    return {
      ok: true,
      json: async () => uploadResponse(file),
    };
  };

  const response = await uploadPdfDocument(file, fetchMock);

  assert.equal(calls.length, 1);
  const [url, options] = calls[0];
  assert.match(url, /\/documents\/upload$/);
  assert.equal(options.method, "POST");
  assert.equal(options.headers.Accept, "application/json");
  assert.equal(Object.hasOwn(options.headers, "Content-Type"), false);
  assert.ok(options.body instanceof FormData);
  assert.equal(options.body.get("file").name, file.name);
  assert.equal(response.document_id, VALID_DOCUMENT_ID);
});

test("document upload UI shows metadata, loading, blocks duplicate submit and succeeds", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const calls = [];
  let resolveRequest;
  globalThis.fetch = (...parameters) => {
    calls.push(parameters);
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
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  });

  await act(async () => {
    renderer = create(React.createElement(DocumentUpload));
  });

  const file = validPdfFile();
  const fileInput = renderer.root.find(
    (node) => node.type === "input" && node.props.type === "file",
  );
  assert.equal(findUploadButton(renderer.root).props.disabled, true);

  await act(async () => fileInput.props.onChange({ target: { files: [file] } }));
  assertVisibleText(renderer.root, file.name);
  assertVisibleText(renderer.root, `${file.size} bytes`);
  assert.equal(findUploadButton(renderer.root).props.disabled, false);

  const form = renderer.root.findByType("form");
  const submitEvent = { preventDefault: () => undefined };
  await act(async () => {
    form.props.onSubmit(submitEvent);
    form.props.onSubmit(submitEvent);
    await Promise.resolve();
  });

  assert.equal(calls.length, 1);
  assertVisibleText(renderer.root, "Subiendo documento...");
  assert.equal(findUploadButton(renderer.root).props.disabled, true);
  assert.equal(fileInput.props.disabled, true);

  await act(async () => {
    resolveRequest({
      ok: true,
      json: async () => uploadResponse(file),
    });
    await Promise.resolve();
  });

  assertVisibleText(renderer.root, "Documento cargado correctamente");
  assert.equal(calls.length, 1);
});

test("document upload UI rejects invalid files and handles backend errors", async (t) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const originalFetch = globalThis.fetch;
  const originalConsoleError = console.error;
  let callCount = 0;
  globalThis.fetch = async () => {
    callCount += 1;
    return { ok: false, status: 415 };
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

  await act(async () => {
    renderer = create(React.createElement(DocumentUpload));
  });

  const fileInput = renderer.root.find(
    (node) => node.type === "input" && node.props.type === "file",
  );
  await act(async () =>
    fileInput.props.onChange({
      target: {
        files: [
          new File(["contenido"], "documento.txt", { type: "text/plain" }),
        ],
      },
    }),
  );
  assertVisibleText(renderer.root, "extensión .pdf");
  assert.equal(findUploadButton(renderer.root).props.disabled, true);
  assert.equal(callCount, 0);

  const validFile = validPdfFile();
  await act(async () =>
    fileInput.props.onChange({ target: { files: [validFile] } }),
  );
  await act(async () => {
    renderer.root
      .findByType("form")
      .props.onSubmit({ preventDefault: () => undefined });
    await Promise.resolve();
  });

  assert.equal(callCount, 1);
  assertVisibleText(
    renderer.root,
    "No fue posible subir el documento. Verifica el archivo",
  );
  assert.equal(findUploadButton(renderer.root).props.disabled, false);
});
