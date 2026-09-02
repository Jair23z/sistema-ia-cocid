from typing import Any

import requests

BASE_URL = "https://api.openalex.org/works"
SELECT_FIELDS = ",".join(
    [
        "id",
        "display_name",
        "authorships",
        "publication_year",
        "publication_date",
        "primary_location",
        "type",
        "doi",
        "cited_by_count",
        "open_access",
        "abstract_inverted_index",
    ]
)


def normalize_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized_value = value.strip()
    return normalized_value or None


def reconstruct_abstract(
    inverted_index: dict[str, list[int]] | None,
) -> str | None:
    """Reconstruct plain text from OpenAlex's inverted abstract index."""
    if not inverted_index:
        return None

    positioned_words = [
        (position, word)
        for word, positions in inverted_index.items()
        for position in positions
    ]

    if not positioned_words:
        return None

    positioned_words.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positioned_words)


def normalize_work(work: dict[str, Any]) -> dict[str, Any]:
    authors = []

    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        author_name = normalize_optional_string(
            author.get("display_name") or authorship.get("raw_author_name")
        )

        if author_name:
            authors.append(author_name)

    primary_location = work.get("primary_location") or {}
    source_data = primary_location.get("source") or {}
    open_access = work.get("open_access") or {}
    openalex_url = normalize_optional_string(work.get("id"))
    openalex_id = None

    if openalex_url:
        openalex_id = openalex_url.rstrip("/").rsplit("/", maxsplit=1)[-1]

    return {
        "id": openalex_url,
        "title": normalize_optional_string(
            work.get("display_name") or work.get("title")
        ),
        "authors": authors,
        "year": work.get("publication_year"),
        "publication_date": normalize_optional_string(work.get("publication_date")),
        "source": normalize_optional_string(
            source_data.get("display_name")
            or primary_location.get("raw_source_name")
        ),
        "publication_type": normalize_optional_string(work.get("type")),
        "doi": normalize_optional_string(work.get("doi")),
        "citations": work.get("cited_by_count"),
        "openalex_id": openalex_id,
        "openalex_url": openalex_url,
        "publication_url": normalize_optional_string(
            primary_location.get("landing_page_url") or work.get("doi")
        ),
        "is_open_access": open_access.get("is_oa"),
        "open_access_status": normalize_optional_string(open_access.get("oa_status")),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
    }


def search_papers(
    query: str,
    limit: int = 10,
    from_year: int | None = None,
    to_year: int | None = None,
    publication_type: str | None = None,
    is_open_access: bool | None = None,
):
    params = {
        "search": query,
        "per-page": limit,
        "select": SELECT_FIELDS,
    }
    filters = []

    if from_year is not None:
        filters.append(f"from_publication_date:{from_year}-01-01")

    if to_year is not None:
        filters.append(f"to_publication_date:{to_year}-12-31")

    if publication_type:
        filters.append(f"type:{publication_type}")

    if is_open_access is not None:
        filters.append(
            f"open_access.is_oa:{str(is_open_access).lower()}"
        )

    if filters:
        params["filter"] = ",".join(filters)

    response = requests.get(BASE_URL, params=params, timeout=20)
    response.raise_for_status()

    data = response.json()
    return [normalize_work(work) for work in data.get("results") or []]


def get_paper_by_id(openalex_id: str):
    response = requests.get(
        f"{BASE_URL}/{openalex_id}",
        params={"select": SELECT_FIELDS},
        timeout=20,
    )
    response.raise_for_status()
    return normalize_work(response.json())
