"""
Async HTTP collector base class with aiohttp and rate limiting.

This module provides an async version of the API_collector base class,
enabling concurrent HTTP requests with configurable rate limiting and
automatic retry logic.

Features:
- Non-blocking async/await API calls with aiohttp
- Per-API rate limiting using asyncio.Semaphore
- Automatic retry with exponential backoff
- Connection pooling and session reuse
- Comprehensive error handling and logging
"""

import asyncio
import logging
import os
import time
from datetime import date
from typing import Optional, Dict, Any

import aiohttp
import yaml

from .collectors import Filter_param


class AsyncAPICollector:
    """
    Async base class for API collectors with aiohttp and rate limiting.

    This class extends the synchronous API_collector pattern to support
    concurrent HTTP requests while respecting API rate limits.

    Key differences from sync version:
    - Uses aiohttp instead of requests for non-blocking I/O
    - Implements asyncio.Semaphore for per-API concurrency control
    - Async/await methods throughout
    - Connection pooling with session reuse
    """

    # Default rate limits (requests per second)
    DEFAULT_RATE_LIMITS = {
        "SemanticScholar": 1.0,
        "OpenAlex": 10.0,
        "Arxiv": 3.0,
        "IEEE": 10.0,
        "Elsevier": 6.0,
        "Springer": 1.5,
        "HAL": 10.0,
        "DBLP": 10.0,
        "GoogleScholar": 2.0,
        "Crossref": 3.0,
    }

    # Per-API concurrency limits (max concurrent requests)
    # Lower values for rate-sensitive APIs
    CONCURRENCY_LIMITS = {
        "SemanticScholar": 1,  # Very conservative
        "OpenAlex": 3,  # Can handle 3 concurrent
        "Arxiv": 2,  # Conservative
        "IEEE": 3,  # Conservative due to daily quota
        "Elsevier": 2,  # Conservative
        "Springer": 1,  # Very conservative
        "HAL": 3,  # Can handle multiple
        "DBLP": 3,  # Can handle multiple
        "GoogleScholar": 1,  # Web scraping - single thread
        "Crossref": 3,  # Can handle multiple
    }

    def __init__(
        self, data_query: Dict[str, Any], data_path: str, api_key: Optional[str] = None
    ):
        """
        Initialize async collector.

        Args:
            data_query: Dictionary with year, keyword, id_collect, total_art, last_page, coll_art, state
            data_path: Output directory path
            api_key: API key for authentication (optional)
        """
        self.api_key = api_key
        self.api_name = "None"  # Override in subclass
        self.filter_param = Filter_param(data_query["year"], data_query["keyword"])
        self.rate_limit = 10.0  # Will be overridden by load_rate_limit_from_config()
        self.concurrency_limit = 1  # Will be overridden
        self.datadir = data_path
        self.collectId = data_query["id_collect"]
        self.total_art = int(data_query["total_art"])
        self.lastpage = int(data_query["last_page"])
        self.nb_art_collected = int(data_query["coll_art"])
        self.big_collect = 0
        self.max_by_page = 100
        self.api_url = ""
        self.state = data_query["state"]

        # Async-specific attributes
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore: Optional[asyncio.Semaphore] = None
        self.request_count = 0
        self.error_count = 0

    def load_rate_limit_from_config(self) -> None:
        """
        Load rate limit and concurrency limit from config file.

        Falls back to DEFAULT_RATE_LIMITS if config not available.
        """
        try:
            config_path = os.path.join(
                os.path.dirname(__file__), "..", "api.config.yml"
            )

            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config = yaml.safe_load(f)

                # Load rate limit
                if (
                    config
                    and "rate_limits" in config
                    and self.api_name in config["rate_limits"]
                ):
                    configured_limit = float(config["rate_limits"][self.api_name])
                    self.rate_limit = configured_limit
                    logging.debug(
                        f"{self.api_name}: Using configured rate limit of {configured_limit} req/sec"
                    )
                else:
                    # Use default
                    self.rate_limit = self.DEFAULT_RATE_LIMITS.get(self.api_name, 10.0)
                    logging.debug(
                        f"{self.api_name}: Using default rate limit of {self.rate_limit} req/sec"
                    )

                # Load concurrency limit from performance config if available
                if config and "performance" in config:
                    perf = config["performance"]
                    max_concurrent = perf.get("max_concurrent_per_api", None)
                    if max_concurrent:
                        self.concurrency_limit = max_concurrent
                    else:
                        self.concurrency_limit = self.CONCURRENCY_LIMITS.get(
                            self.api_name, 1
                        )
                else:
                    self.concurrency_limit = self.CONCURRENCY_LIMITS.get(
                        self.api_name, 1
                    )

        except Exception as e:
            logging.warning(
                f"{self.api_name}: Could not load rate limit from config: {e}"
            )
            self.rate_limit = self.DEFAULT_RATE_LIMITS.get(self.api_name, 10.0)
            self.concurrency_limit = self.CONCURRENCY_LIMITS.get(self.api_name, 1)

    async def create_session(self) -> aiohttp.ClientSession:
        """
        Create an aiohttp ClientSession with connection pooling.

        Returns:
            Configured aiohttp ClientSession
        """
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(
                limit_per_host=self.concurrency_limit, limit=100, ttl_dns_cache=300
            )
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30, connect=10, sock_read=10),
            )
        return self.session

    async def close_session(self) -> None:
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            # Wait a bit for connections to close
            await asyncio.sleep(0.25)

    async def api_call_async(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Make an async HTTP request with rate limiting and retry logic.

        Args:
            url: URL to request
            method: HTTP method (GET, POST, etc.)
            params: Query parameters
            max_retries: Number of retry attempts

        Returns:
            Response JSON as dictionary

        Raises:
            Exception: If all retry attempts fail
        """
        # Ensure semaphore exists
        if self.semaphore is None:
            self.semaphore = asyncio.Semaphore(self.concurrency_limit)

        # Respect rate limit: wait between requests
        delay_between_requests = 1.0 / self.rate_limit

        async with self.semaphore:
            session = await self.create_session()
            last_exception = None

            for attempt in range(max_retries):
                try:
                    logging.debug(
                        f"{self.api_name} API: Request {method} {url} (attempt {attempt + 1})"
                    )

                    async with session.request(
                        method, url, params=params, headers=self._get_headers()
                    ) as response:
                        self.request_count += 1

                        # Check for HTTP errors
                        if response.status == 429:  # Rate limit
                            wait_time = 2**attempt
                            logging.warning(
                                f"{self.api_name} API rate limit (429). "
                                f"Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})"
                            )
                            if attempt < max_retries - 1:
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                raise aiohttp.ClientResponseError(
                                    request_info=response.request_info,
                                    history=response.history,
                                    status=response.status,
                                    message="Rate limit exceeded after retries",
                                )

                        elif response.status in [401, 403]:  # Auth error
                            logging.error(
                                f"{self.api_name} API authentication failed ({response.status}). "
                                "Check API key and credentials."
                            )
                            response.raise_for_status()

                        elif response.status >= 500:  # Server error
                            wait_time = 2**attempt
                            logging.warning(
                                f"{self.api_name} API server error ({response.status}). "
                                f"Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})"
                            )
                            if attempt < max_retries - 1:
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                response.raise_for_status()

                        response.raise_for_status()

                        # Successfully got response
                        logging.debug(
                            f"{self.api_name} API: Request successful (status {response.status})"
                        )

                        try:
                            data = await response.json()

                            # Sleep AFTER successful request to respect rate limit
                            # This ensures we don't exceed X requests per second
                            await asyncio.sleep(delay_between_requests)

                            return data
                        except asyncio.TimeoutError as e:
                            logging.error(
                                f"{self.api_name} API: Response timeout while reading JSON"
                            )
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2**attempt)
                                continue
                            else:
                                raise

                except aiohttp.ClientConnectorError as e:
                    last_exception = e
                    wait_time = 2**attempt
                    logging.warning(
                        f"{self.api_name} API connection error. "
                        f"Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        self.error_count += 1
                        raise

                except (asyncio.TimeoutError, aiohttp.ClientSSLError) as e:
                    last_exception = e
                    wait_time = 2**attempt
                    logging.warning(
                        f"{self.api_name} API timeout/SSL error. "
                        f"Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        self.error_count += 1
                        raise

                except aiohttp.ClientResponseError as e:
                    last_exception = e
                    logging.error(
                        f"{self.api_name} API HTTP error {e.status}: {str(e)}"
                    )
                    if e.status >= 500 and attempt < max_retries - 1:
                        await asyncio.sleep(2**attempt)
                        continue
                    else:
                        self.error_count += 1
                        raise

                except aiohttp.ClientError as e:
                    last_exception = e
                    logging.error(f"{self.api_name} API client error: {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2**attempt)
                        continue
                    else:
                        self.error_count += 1
                        raise

            # Exhausted retries
            if last_exception:
                logging.error(
                    f"{self.api_name} API: All {max_retries} retry attempts exhausted"
                )
                self.error_count += 1
                raise last_exception
            else:
                raise RuntimeError(
                    f"{self.api_name} API: Failed after {max_retries} attempts"
                )

    def _get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for API request.

        Override in subclass to add API-specific headers.

        Returns:
            Dictionary of HTTP headers
        """
        headers = {
            "User-Agent": "SciLEx/1.0 (https://github.com/yourusername/SciLEx)",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def fetch_multiple_pages(
        self, urls: list, max_concurrent: Optional[int] = None
    ) -> list:
        """
        Fetch multiple URLs concurrently while respecting rate limits.

        This is useful for collecting multiple pages in parallel.

        Args:
            urls: List of URLs to fetch
            max_concurrent: Override concurrency limit (optional)

        Returns:
            List of response dictionaries in original order
        """
        if max_concurrent is None:
            max_concurrent = self.concurrency_limit

        # Create a semaphore for concurrent requests
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_semaphore(url: str) -> tuple:
            async with semaphore:
                try:
                    result = await self.api_call_async(url)
                    return (url, result, None)
                except Exception as e:
                    return (url, None, e)

        # Fetch all URLs concurrently
        tasks = [fetch_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Return results in order
        return results

    async def run_collect_async(self) -> Dict[str, Any]:
        """
        Async version of runCollect.

        This should be overridden in subclasses to implement specific
        collection logic using async methods.

        Returns:
            State data dictionary with collection results
        """
        state_data = {
            "state": self.state,
            "last_page": self.lastpage,
            "total_art": self.total_art,
            "coll_art": self.nb_art_collected,
            "update_date": str(date.today()),
            "id_collect": self.collectId,
        }

        logging.warning(
            f"{self.api_name}: run_collect_async() not implemented. "
            "Override in subclass."
        )

        return state_data

    def set_lastpage(self, lastpage: int) -> None:
        """Set the last page collected."""
        self.lastpage = lastpage

    def get_lastpage(self) -> int:
        """Get the last page collected."""
        return self.lastpage

    def set_collectId(self, collectId) -> None:
        """Set the collection ID."""
        self.collectId = collectId

    def get_collectId(self):
        """Get the collection ID."""
        return self.collectId

    def get_api_name(self) -> str:
        """Get the API name."""
        return self.api_name

    def get_keywords(self):
        """Get the keywords."""
        return self.filter_param.get_keywords()

    def get_year(self) -> int:
        """Get the year."""
        return self.filter_param.get_year()

    def get_dataDir(self) -> str:
        """Get the data directory."""
        return self.datadir

    def get_ratelimit(self) -> float:
        """Get the rate limit."""
        return self.rate_limit

    def get_max_by_page(self) -> int:
        """Get max results per page."""
        return self.max_by_page

    def get_apiDir(self) -> str:
        """Get the API-specific directory (e.g., output/collect_NAME/SemanticScholar)."""
        return os.path.join(self.datadir, self.api_name)

    def get_collectDir(self) -> str:
        """Get the collection-specific directory (e.g., output/collect_NAME/SemanticScholar/0)."""
        return os.path.join(self.get_apiDir(), str(self.collectId))

    def createCollectDir(self) -> None:
        """Create the collection directory with proper structure."""
        collect_dir = self.get_collectDir()
        if not os.path.isdir(collect_dir):
            os.makedirs(collect_dir)

    def savePageResults(self, page_data: Dict, page_num: int) -> None:
        """
        Save page results to file with proper directory structure.

        Args:
            page_data: Dictionary with page results
            page_num: Page number
        """
        import json

        # Create directory structure: output/collect_NAME/API_NAME/COLLECT_ID/
        collect_dir = self.get_collectDir()
        if not os.path.isdir(collect_dir):
            os.makedirs(collect_dir)

        page_file = os.path.join(collect_dir, f"page_{page_num}")

        try:
            with open(page_file, "w", encoding="utf-8") as f:
                json.dump(page_data, f, ensure_ascii=False, indent=2)
            logging.debug(f"Saved page {page_num} to {page_file}")
        except Exception as e:
            logging.error(f"Error saving page {page_num}: {str(e)}")
            raise

    def get_offset(self, page_num: int) -> int:
        """
        Calculate offset for pagination.

        Override in subclass if API uses offset-based pagination.

        Args:
            page_num: Page number (1-indexed)

        Returns:
            Offset value for the API
        """
        return (page_num - 1) * self.max_by_page
