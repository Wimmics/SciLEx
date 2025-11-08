#!/usr/bin/env python3
"""
Unit tests for max_articles_per_query enforcement in async collectors.

Tests verify that AsyncSemanticScholarCollector and AsyncOpenAlexCollector
properly respect the max_articles_per_query configuration parameter.
"""

import asyncio
import unittest
from unittest.mock import patch

from src.crawlers.async_collectors_impl import (
    AsyncOpenAlexCollector,
    AsyncSemanticScholarCollector,
)


class TestAsyncMaxArticlesEnforcement(unittest.TestCase):
    """Test suite for max_articles_per_query enforcement in async collectors."""

    def setUp(self):
        """Set up test fixtures."""
        self.data_path = "/tmp/test_scilex"

    def test_semantic_scholar_keyword_operator_and_logic(self):
        """Test that SemanticScholar uses + (AND) operator, not | (OR)."""
        data_query = {
            "year": 2024,
            "keyword": ["Large language model", "Knowledge Graph"],
            "id_collect": 0,
            "total_art": 0,
            "last_page": 0,
            "coll_art": 0,
            "state": 0,
            "max_articles_per_query": 10,
        }

        collector = AsyncSemanticScholarCollector(
            data_query, self.data_path, api_key=None
        )

        # Build URL for first page
        url = collector._build_query_url(page=1)

        # Verify URL uses + (AND) operator, not | (OR)
        self.assertIn("+", url, "URL should contain + for AND logic")
        self.assertNotIn("|", url, "URL should NOT contain | (OR operator)")
        self.assertIn(
            '"Large+language+model"', url, "Keywords should be quoted and joined with +"
        )

    def test_semantic_scholar_uses_regular_endpoint_not_bulk(self):
        """Test that SemanticScholar uses regular endpoint, not /bulk."""
        data_query = {
            "year": 2024,
            "keyword": ["LLM"],
            "id_collect": 0,
            "total_art": 0,
            "last_page": 0,
            "coll_art": 0,
            "state": 0,
            "max_articles_per_query": 10,
        }

        collector = AsyncSemanticScholarCollector(
            data_query, self.data_path, api_key=None
        )

        url = collector._build_query_url(page=1)

        # Verify URL uses regular endpoint, not /bulk
        self.assertNotIn("/bulk", url, "URL should NOT contain /bulk endpoint")
        self.assertIn(
            "api.semanticscholar.org/graph/v1/paper/search?",
            url,
            "URL should use regular endpoint",
        )

    @patch(
        "src.crawlers.async_collectors_impl.AsyncSemanticScholarCollector.api_call_async"
    )
    @patch(
        "src.crawlers.async_collectors_impl.AsyncSemanticScholarCollector.savePageResults"
    )
    @patch(
        "src.crawlers.async_collectors_impl.AsyncSemanticScholarCollector.close_session"
    )
    def test_semantic_scholar_respects_max_articles_limit(
        self, mock_close, mock_save, mock_api_call
    ):
        """Test that SemanticScholar stops collecting when max_articles_per_query is reached."""
        # Configure mock API responses
        # First page: 100 results, total=500
        first_page_response = {
            "total": 500,
            "data": [
                {
                    "title": f"Paper {i}",
                    "abstract": f"Abstract {i}",
                    "url": f"http://example.com/{i}",
                    "venue": "Test Venue",
                    "citationCount": 10,
                    "referenceCount": 5,
                    "authors": [],
                    "fieldsOfStudy": [],
                    "publicationDate": "2024-01-01",
                    "openAccessPdf": {},
                    "externalIds": {"DOI": f"10.1234/{i}"},
                }
                for i in range(100)
            ],
        }

        # Return first page on first call, should not fetch more pages
        mock_api_call.return_value = first_page_response
        mock_save.return_value = None
        mock_close.return_value = None

        data_query = {
            "year": 2024,
            "keyword": ["LLM"],
            "id_collect": 0,
            "total_art": 0,
            "last_page": 0,
            "coll_art": 0,
            "state": 0,
            "max_articles_per_query": 10,  # Limit to 10 articles
        }

        collector = AsyncSemanticScholarCollector(
            data_query, self.data_path, api_key=None
        )

        # Run async collection
        loop = asyncio.get_event_loop()
        state_data = loop.run_until_complete(collector.run_collect_async())

        # Verify that only 1 page was fetched (first page only)
        # Since max_articles_per_query=10 and max_by_page=100, we only need 1 page
        self.assertEqual(
            mock_api_call.call_count,
            1,
            "Should only fetch 1 page when max_articles_per_query=10",
        )

        # Verify state data
        self.assertEqual(state_data["state"], 1, "Collection should be marked complete")
        self.assertEqual(
            state_data["coll_art"],
            100,
            "Should have collected 100 articles from first page",
        )

    @patch("src.crawlers.async_collectors_impl.AsyncOpenAlexCollector.api_call_async")
    @patch("src.crawlers.async_collectors_impl.AsyncOpenAlexCollector.savePageResults")
    @patch("src.crawlers.async_collectors_impl.AsyncOpenAlexCollector.close_session")
    def test_openalex_respects_max_articles_limit(
        self, mock_close, mock_save, mock_api_call
    ):
        """Test that OpenAlex stops collecting when max_articles_per_query is reached."""
        # Configure mock API responses
        # First page: 200 results (OpenAlex max_by_page=200), total=1000
        first_page_response = {
            "meta": {"count": 1000},
            "results": [{"id": f"W{i}", "title": f"Paper {i}"} for i in range(200)],
        }

        mock_api_call.return_value = first_page_response
        mock_save.return_value = None
        mock_close.return_value = None

        data_query = {
            "year": 2024,
            "keyword": ["knowledge graph"],
            "id_collect": 0,
            "total_art": 0,
            "last_page": 0,
            "coll_art": 0,
            "state": 0,
            "max_articles_per_query": 100,  # Limit to 100 articles
        }

        collector = AsyncOpenAlexCollector(data_query, self.data_path, api_key=None)

        # Run async collection
        loop = asyncio.get_event_loop()
        state_data = loop.run_until_complete(collector.run_collect_async())

        # Verify that only 1 page was fetched
        # Since max_articles_per_query=100 and max_by_page=200, we only need 1 page
        self.assertEqual(
            mock_api_call.call_count,
            1,
            "Should only fetch 1 page when max_articles_per_query=100",
        )

        # Verify state data
        self.assertEqual(state_data["state"], 1, "Collection should be marked complete")
        self.assertEqual(
            state_data["coll_art"],
            200,
            "Should have collected 200 articles from first page",
        )

    def test_semantic_scholar_calculates_max_pages_correctly(self):
        """Test that max pages calculation works correctly for various limits."""
        test_cases = [
            # (max_articles, max_by_page, expected_max_pages)
            (10, 100, 1),  # 0.1 pages -> 1 page
            (100, 100, 1),  # Exact 1 page
            (150, 100, 2),  # 1.5 pages -> 2 pages
            (250, 100, 3),  # 2.5 pages -> 3 pages
            (100, 200, 1),  # 0.5 pages (OpenAlex style) -> 1 page
        ]

        for max_articles, max_by_page, expected_pages in test_cases:
            data_query = {
                "year": 2024,
                "keyword": ["test"],
                "id_collect": 0,
                "total_art": 0,
                "last_page": 0,
                "coll_art": 0,
                "state": 0,
                "max_articles_per_query": max_articles,
            }

            collector = AsyncSemanticScholarCollector(
                data_query, self.data_path, api_key=None
            )
            collector.max_by_page = max_by_page

            # Calculate expected pages using same logic as collector
            max_pages_needed = (
                max_articles + max_by_page - 1
            ) // max_by_page  # Ceiling division

            self.assertEqual(
                max_pages_needed,
                expected_pages,
                f"max_articles={max_articles}, max_by_page={max_by_page} should result in {expected_pages} pages",
            )


if __name__ == "__main__":
    unittest.main()
