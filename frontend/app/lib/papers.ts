export type Paper = {
  id: string | null;
  title: string | null;
  authors: string[];
  year: number | null;
  publication_date: string | null;
  source: string | null;
  publication_type: string | null;
  doi: string | null;
  citations: number | null;
  openalex_id: string | null;
  openalex_url: string | null;
  publication_url: string | null;
  is_open_access: boolean | null;
  open_access_status: string | null;
  abstract: string | null;
};

export type PublicationTypeFilter =
  | ""
  | "article"
  | "review"
  | "book"
  | "book-chapter"
  | "dissertation"
  | "preprint";

export type OpenAccessFilter = "" | "true" | "false";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export const PAPER_SEARCH_STORAGE_KEY = "cocid-ai:paper-search";

export const PUBLICATION_TYPE_OPTIONS: ReadonlyArray<{
  value: Exclude<PublicationTypeFilter, "">;
  label: string;
}> = [
  { value: "article", label: "Artículo" },
  { value: "review", label: "Revisión" },
  { value: "book", label: "Libro" },
  { value: "book-chapter", label: "Capítulo de libro" },
  { value: "dissertation", label: "Tesis" },
  { value: "preprint", label: "Preprint" },
];

const PUBLICATION_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  PUBLICATION_TYPE_OPTIONS.map((option) => [option.value, option.label]),
);

const OPEN_ACCESS_STATUS_LABELS: Record<string, string> = {
  diamond: "diamante",
  gold: "dorado",
  green: "verde",
  hybrid: "híbrido",
  bronze: "bronce",
};

export function displayValue(value: string | null, fallback = "No disponible") {
  return value?.trim() || fallback;
}

export function displayAuthors(authors: string[], maximumAuthors?: number) {
  const availableAuthors = authors.filter((author) => author.trim());

  if (availableAuthors.length === 0) {
    return "Autores no disponibles";
  }

  if (maximumAuthors && availableAuthors.length > maximumAuthors) {
    const remainingAuthors = availableAuthors.length - maximumAuthors;
    return `${availableAuthors.slice(0, maximumAuthors).join(", ")} y ${remainingAuthors} más`;
  }

  return availableAuthors.join(", ");
}

export function formatDoi(doi: string) {
  return doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "");
}

export function getSafeExternalUrl(value: string | null) {
  if (!value) {
    return null;
  }

  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:"
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}

export function formatPublicationDate(publicationDate: string | null) {
  if (!publicationDate) {
    return "No disponible";
  }

  const dateParts = publicationDate.split("-");
  return dateParts.length === 3
    ? dateParts.reverse().join("/")
    : publicationDate;
}

export function formatPublicationType(publicationType: string | null) {
  if (!publicationType) {
    return "No disponible";
  }

  return PUBLICATION_TYPE_LABELS[publicationType] ?? publicationType;
}

export function getOpenAccessLabel(paper: Paper) {
  if (paper.open_access_status === "closed") {
    return "Acceso cerrado";
  }

  if (paper.open_access_status) {
    const translatedStatus =
      OPEN_ACCESS_STATUS_LABELS[paper.open_access_status] ??
      paper.open_access_status;

    return `Acceso abierto (${translatedStatus})`;
  }

  if (paper.is_open_access === true) {
    return "Acceso abierto";
  }

  if (paper.is_open_access === false) {
    return "Acceso cerrado";
  }

  return null;
}

export function getOpenAccessClassName(paper: Paper) {
  const isOpenAccess = paper.open_access_status
    ? paper.open_access_status !== "closed"
    : paper.is_open_access === true;

  return isOpenAccess
    ? "bg-cocid-turquoise text-cocid-navy"
    : "bg-cocid-graphite text-cocid-white";
}

export function isPaper(value: unknown): value is Paper {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const paper = value as Record<string, unknown>;
  const nullableStringFields = [
    "id",
    "title",
    "publication_date",
    "source",
    "publication_type",
    "doi",
    "openalex_id",
    "openalex_url",
    "publication_url",
    "open_access_status",
    "abstract",
  ];
  const nullableNumberFields = ["year", "citations"];

  return (
    Array.isArray(paper.authors) &&
    paper.authors.every((author) => typeof author === "string") &&
    nullableStringFields.every(
      (field) => paper[field] === null || typeof paper[field] === "string",
    ) &&
    nullableNumberFields.every(
      (field) => paper[field] === null || typeof paper[field] === "number",
    ) &&
    (paper.is_open_access === null ||
      typeof paper.is_open_access === "boolean")
  );
}
