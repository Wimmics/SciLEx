"""
Async wrapper that bridges synchronous API collectors with async runtime.

This provides a pragmatic Phase 1 approach:
1. Keep existing sync collectors unchanged
2. Wrap them with async context using asyncio.to_thread()
3. Add per-API rate limiting and concurrency control
4. Enable gradual migration to full async collectors

This allows us to get async benefits (concurrency, rate limiting) without
rewriting all 10+ collectors immediately.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from src.crawlers.collectors import (
    SemanticScholar_collector,
    IEEE_collector,
    Elsevier_collector,
    Springer_collector,
    DBLP_collector,
    OpenAlex_collector,
    HAL_collector,
    Arxiv_collector,
    GoogleScholarCollector,
    Istex_collector,
)


class AsyncCollectorWrapper:
    """
    Wraps synchronous API collectors with async context and rate limiting.

    Key features:
    - Uses asyncio.to_thread() to run sync code without blocking
    - Per-API semaphores for concurrency control
    - Async/await interface for collection
    - Maintains backward compatibility with existing collectors
    """

    # Concurrency limits (max concurrent collections per API)
    CONCURRENCY_LIMITS = {
        "SemanticScholar": 1,  # Very conservative (1 req/sec)
        "OpenAlex": 3,  # Can handle 3 concurrent (10 req/sec)
        "Arxiv": 2,  # Conservative (3 req/sec)
        "IEEE": 3,  # Conservative (10 req/sec, 200/day quota)
        "Elsevier": 2,  # Conservative (6 req/sec)
        "Springer": 1,  # Very conservative (1.5 req/sec)
        "HAL": 3,  # Can handle multiple (10 req/sec)
        "DBLP": 3,  # Can handle multiple (10 req/sec)
        "GoogleScholar": 1,  # Single thread (web scraping)
        "ISTEX": 2,  # Conservative (10 req/sec available)
        "Crossref": 3,  # Can handle multiple (3 req/sec)
    }

    # Mapping of API names to collector classes
    COLLECTOR_CLASSES = {
        "SemanticScholar": SemanticScholar_collector,
        "IEEE": IEEE_collector,
        "Elsevier": Elsevier_collector,
        "Springer": Springer_collector,
        "DBLP": DBLP_collector,
        "OpenAlex": OpenAlex_collector,
        "HAL": HAL_collector,
        "Arxiv": Arxiv_collector,
        "GoogleScholar": GoogleScholarCollector,
        "ISTEX": Istex_collector,
    }

    def __init__(self):
        """Initialize wrapper with per-API semaphores."""
        self.semaphores: Dict[str, asyncio.Semaphore] = {}
        self._initialize_semaphores()

    def _initialize_semaphores(self) -> None:
        """Create semaphores for each API."""
        for api_name, limit in self.CONCURRENCY_LIMITS.items():
            self.semaphores[api_name] = asyncio.Semaphore(limit)

    async def run_collection_async(
        self,
        api_name: str,
        data_query: Dict[str, Any],
        data_path: str,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run a collection asynchronously using semaphore for rate limiting.

        Args:
            api_name: Name of API (e.g., 'SemanticScholar')
            data_query: Query configuration
            data_path: Output directory
            api_key: API authentication key

        Returns:
            State data dictionary with collection results
        """
        if api_name not in self.COLLECTOR_CLASSES:
            raise ValueError(f"Unknown API: {api_name}")

        # Acquire semaphore (respect concurrency limit)
        semaphore = self.semaphores.get(api_name)
        if not semaphore:
            semaphore = asyncio.Semaphore(1)

        async with semaphore:
            # Run sync collector in thread pool (non-blocking)
            result = await asyncio.to_thread(
                self._run_sync_collector, api_name, data_query, data_path, api_key
            )
            return result

    def _run_sync_collector(
        self,
        api_name: str,
        data_query: Dict[str, Any],
        data_path: str,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the synchronous collector (runs in thread pool).

        Args:
            api_name: Name of API
            data_query: Query configuration
            data_path: Output directory
            api_key: API key

        Returns:
            State data from runCollect()
        """
        try:
            # Get collector class
            collector_class = self.COLLECTOR_CLASSES.get(api_name)
            if not collector_class:
                return {
                    "state": -1,
                    "error": f"Unknown API: {api_name}",
                    "last_page": 0,
                }

            # Instantiate collector
            collector = collector_class(data_query, data_path, api_key)

            # Run collection
            logging.info(f"Starting async-wrapped collection for {api_name}")
            state_data = collector.runCollect()

            logging.info(
                f"Completed async-wrapped collection for {api_name}: "
                f"{state_data.get('coll_art', 0)} papers collected"
            )

            # Close HTTP session to free connections (Phase 1 optimization)
            if hasattr(collector, "close_session"):
                collector.close_session()

            return state_data

        except Exception as e:
            logging.error(f"Error in async collection for {api_name}: {str(e)}")
            return {"state": -1, "error": str(e), "last_page": 0, "coll_art": 0}

    async def run_collections_parallel(self, collections: list) -> list:
        """
        Run multiple collections in parallel with rate limiting.

        Args:
            collections: List of dicts with keys:
                - api: API name
                - query: data_query dict
                - path: output path
                - key: API key (optional)

        Returns:
            List of state results in original order
        """
        tasks = [
            self.run_collection_async(
                collection["api"],
                collection["query"],
                collection["path"],
                collection.get("key"),
            )
            for collection in collections
        ]

        # Run all concurrently (each respects its API's semaphore)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logging.error(f"Collection {i} failed with exception: {str(result)}")
                final_results.append(
                    {"state": -1, "error": str(result), "last_page": 0}
                )
            else:
                final_results.append(result)

        return final_results

    async def run_collection_batch_by_api(
        self,
        api_name: str,
        queries: list,
        base_path: str,
        api_key: Optional[str] = None,
    ) -> list:
        """
        Run multiple queries for the same API sequentially.

        Benefits: Single connection reuse, better session pooling

        Args:
            api_name: API name
            queries: List of data_query dicts
            base_path: Base output path
            api_key: API key

        Returns:
            List of state results
        """
        results = []

        # Run queries sequentially for same API (reuse connection)
        for i, query in enumerate(queries):
            # Each query gets unique subdir
            query_path = f"{base_path}/{api_name}/query_{i:03d}"

            result = await self.run_collection_async(
                api_name, query, query_path, api_key
            )
            results.append(result)

        return results

    def set_concurrency_limit(self, api_name: str, limit: int) -> None:
        """
        Set concurrency limit for an API at runtime.

        Args:
            api_name: API name
            limit: Max concurrent requests
        """
        self.semaphores[api_name] = asyncio.Semaphore(limit)
        logging.info(f"Set {api_name} concurrency limit to {limit}")


async def run_wrapper_example():
    """Example usage of AsyncCollectorWrapper."""
    wrapper = AsyncCollectorWrapper()

    # Example: Run multiple collections in parallel
    collections = [
        {
            "api": "SemanticScholar",
            "query": {
                "year": 2024,
                "keyword": ["knowledge graph"],
                "id_collect": 0,
                "total_art": 0,
                "last_page": 0,
                "coll_art": 0,
                "state": -1,
            },
            "path": "/tmp/scilex/semantic_scholar",
            "key": "YOUR_API_KEY",
        }
    ]

    results = await wrapper.run_collections_parallel(collections)
    print(f"Results: {results}")


if __name__ == "__main__":
    asyncio.run(run_wrapper_example())
