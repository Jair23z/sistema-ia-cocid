import unittest
from unittest.mock import Mock, patch

from app.services.openalex import (
    BASE_URL,
    SELECT_FIELDS,
    get_paper_by_id,
    normalize_work,
    reconstruct_abstract,
    search_papers,
)


class ReconstructAbstractTests(unittest.TestCase):
    def test_reconstructs_words_in_position_order(self):
        inverted_index = {
            "again.": [4],
            "science": [1, 3],
            "Data": [0],
            "is": [2],
        }

        abstract = reconstruct_abstract(inverted_index)

        self.assertEqual(abstract, "Data science is science again.")

    def test_returns_none_for_missing_or_empty_index(self):
        self.assertIsNone(reconstruct_abstract(None))
        self.assertIsNone(reconstruct_abstract({}))


class NormalizeWorkTests(unittest.TestCase):
    def test_normalizes_complete_work(self):
        work = {
            "id": "https://openalex.org/W123",
            "display_name": "A scientific paper",
            "authorships": [
                {"author": {"display_name": "Ada Lovelace"}},
                {"author": {}, "raw_author_name": "Alan Turing"},
            ],
            "publication_year": 2026,
            "publication_date": "2026-08-28",
            "primary_location": {
                "landing_page_url": "https://example.org/paper",
                "source": {"display_name": "Journal of Examples"},
            },
            "type": "article",
            "doi": "https://doi.org/10.1234/example",
            "cited_by_count": 42,
            "open_access": {"is_oa": True, "oa_status": "gold"},
            "abstract_inverted_index": {
                "A": [0],
                "summary.": [1],
            },
        }

        paper = normalize_work(work)

        self.assertEqual(
            paper,
            {
                "id": "https://openalex.org/W123",
                "title": "A scientific paper",
                "authors": ["Ada Lovelace", "Alan Turing"],
                "year": 2026,
                "publication_date": "2026-08-28",
                "source": "Journal of Examples",
                "publication_type": "article",
                "doi": "https://doi.org/10.1234/example",
                "citations": 42,
                "openalex_id": "W123",
                "openalex_url": "https://openalex.org/W123",
                "publication_url": "https://example.org/paper",
                "is_open_access": True,
                "open_access_status": "gold",
                "abstract": "A summary.",
            },
        )

    def test_handles_missing_optional_values(self):
        paper = normalize_work({})

        self.assertEqual(paper["authors"], [])
        for field, value in paper.items():
            if field != "authors":
                self.assertIsNone(value, field)

    def test_converts_blank_strings_to_missing_values(self):
        paper = normalize_work(
            {
                "id": " ",
                "display_name": " ",
                "authorships": [
                    {"author": {"display_name": "  "}},
                ],
                "primary_location": {
                    "landing_page_url": " ",
                    "source": {"display_name": " "},
                },
                "doi": " ",
                "open_access": {"oa_status": " "},
            }
        )

        self.assertEqual(paper["authors"], [])
        self.assertIsNone(paper["id"])
        self.assertIsNone(paper["title"])
        self.assertIsNone(paper["source"])
        self.assertIsNone(paper["doi"])
        self.assertIsNone(paper["publication_url"])
        self.assertIsNone(paper["open_access_status"])


class SearchPapersTests(unittest.TestCase):
    @patch("app.services.openalex.requests.get")
    def test_requests_selected_fields_and_normalizes_results(self, mock_get):
        response = Mock()
        response.json.return_value = {
            "results": [
                {
                    "id": "https://openalex.org/W456",
                    "display_name": "Test result",
                }
            ]
        }
        mock_get.return_value = response

        papers = search_papers("artificial intelligence", limit=5)

        mock_get.assert_called_once_with(
            BASE_URL,
            params={
                "search": "artificial intelligence",
                "per-page": 5,
                "select": SELECT_FIELDS,
            },
            timeout=20,
        )
        response.raise_for_status.assert_called_once_with()
        self.assertEqual(papers[0]["openalex_id"], "W456")
        self.assertEqual(papers[0]["title"], "Test result")

    @patch("app.services.openalex.requests.get")
    def test_sends_search_filters_to_openalex(self, mock_get):
        response = Mock()
        response.json.return_value = {"results": []}
        mock_get.return_value = response

        search_papers(
            "education",
            limit=25,
            from_year=2020,
            to_year=2025,
            publication_type="review",
            is_open_access=True,
        )

        mock_get.assert_called_once_with(
            BASE_URL,
            params={
                "search": "education",
                "per-page": 25,
                "select": SELECT_FIELDS,
                "filter": (
                    "from_publication_date:2020-01-01,"
                    "to_publication_date:2025-12-31,"
                    "type:review,open_access.is_oa:true"
                ),
            },
            timeout=20,
        )


class GetPaperByIdTests(unittest.TestCase):
    @patch("app.services.openalex.requests.get")
    def test_requests_and_normalizes_one_work(self, mock_get):
        response = Mock()
        response.json.return_value = {
            "id": "https://openalex.org/W789",
            "display_name": "Detailed paper",
        }
        mock_get.return_value = response

        paper = get_paper_by_id("W789")

        mock_get.assert_called_once_with(
            f"{BASE_URL}/W789",
            params={"select": SELECT_FIELDS},
            timeout=20,
        )
        response.raise_for_status.assert_called_once_with()
        self.assertEqual(paper["openalex_id"], "W789")
        self.assertEqual(paper["title"], "Detailed paper")


if __name__ == "__main__":
    unittest.main()
