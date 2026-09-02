from pydantic import BaseModel


class Paper(BaseModel):
    id: str | None
    title: str | None
    authors: list[str]
    year: int | None
    publication_date: str | None
    source: str | None
    publication_type: str | None
    doi: str | None
    citations: int | None
    openalex_id: str | None
    openalex_url: str | None
    publication_url: str | None
    is_open_access: bool | None
    open_access_status: str | None
    abstract: str | None
