import json
import logging
import math
import os
import time
from datetime import date

import requests
import yaml
from ratelimit import limits, sleep_and_retry

from src.config_defaults import DEFAULT_RATE_LIMITS
from src.constants import CircuitBreakerConfig, RateLimitBackoffConfig
from src.crawlers.circuit_breaker import CircuitBreakerOpenError, CircuitBreakerRegistry


class Filter_param:
    def __init__(self, year, keywords, max_articles_per_query=-1):
        # Initialize the parameters
        self.year = year
        # Keywords is now a list of lists to support multiple sets
        self.keywords = keywords
        # Maximum articles per query (-1 = unlimited)
        self.max_articles_per_query = max_articles_per_query

    def get_dict_param(self):
        # Return the instance's dictionary representation
        return self.__dict__

    def get_year(self):
        return self.year

    def get_keywords(self):
        return self.keywords

    def get_max_articles_per_query(self):
        return self.max_articles_per_query


class API_collector:
    # Default rate limits (fallback if config not available)

    def __init__(self, data_query, data_path, api_key):
        self.api_key = api_key
        self.api_name = "None"
        self.filter_param = Filter_param(
            data_query["year"],
            data_query["keyword"],
            data_query.get(
                "max_articles_per_query", -1
            ),  # Default to -1 (unlimited) if not in config
        )
        self.rate_limit = 10  # Will be overridden by load_rate_limit_from_config()
        self.datadir = data_path
        self.collectId = data_query["id_collect"]
        self.total_art = int(data_query["total_art"])
        self.lastpage = int(data_query["last_page"])
        self.nb_art_collected = int(data_query["coll_art"])
        self.big_collect = 0
        self.max_by_page = 100
        self.api_url = ""
        self.state = data_query["state"]

        # Connection pooling: Create persistent session for better performance
        self.session = requests.Session()
        # Configure keep-alive and connection pooling
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0,  # We handle retries manually
            pool_block=False,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Batch file I/O: Buffer results before writing to reduce disk I/O
        self._result_buffer = []
        self._buffer_size = 10  # Write every 10 pages

    def close_session(self):
        """Close the HTTP session and release connections."""
        # Flush any remaining buffered results
        if hasattr(self, "_result_buffer") and self._result_buffer:
            self._flush_buffer()

        # Close HTTP session
        if hasattr(self, "session") and self.session:
            self.session.close()
            logging.debug(f"{self.api_name}: Session closed")

    def load_rate_limit_from_config(self):
        """
        Load rate limit for this API from the configuration file.
        Falls back to DEFAULT_RATE_LIMITS if config is not available.

        This method should be called after self.api_name is set in subclass __init__.
        """
        try:
            # Try to find api.config.yml in the src directory
            config_path = os.path.join(
                os.path.dirname(__file__), "..", "api.config.yml"
            )

            if os.path.exists(config_path):
                with open(config_path) as f:
                    config = yaml.safe_load(f)

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
                    return
        except Exception as e:
            logging.warning(
                f"{self.api_name}: Could not load rate limit from config: {e}. Using default."
            )

        # Fall back to default rate limits
        if self.api_name in DEFAULT_RATE_LIMITS:
            default_limit = DEFAULT_RATE_LIMITS[self.api_name]
            self.rate_limit = default_limit
            logging.debug(
                f"{self.api_name}: Using default rate limit of {default_limit} req/sec"
            )
        else:
            # Keep the existing rate_limit value (usually set in subclass)
            logging.debug(
                f"{self.api_name}: Using hardcoded rate limit of {self.rate_limit} req/sec"
            )

    def log_api_usage(
        self, response: requests.Response | None, page: int, results_count: int
    ):
        """
        Log API usage statistics for monitoring and debugging.

        Args:
            response: The API response object (or None if request failed)
            page: The current page number
            results_count: Number of results retrieved
        """
        if response is None:
            logging.warning(
                f"{self.api_name} - Page {page}: Request failed, no response received"
            )
            return

        # Log basic request info
        log_data = {
            "api": self.api_name,
            "page": page,
            "results_count": results_count,
            "status_code": response.status_code,
            "response_time_ms": int(response.elapsed.total_seconds() * 1000),
        }

        # Extract rate limit info from common header names
        rate_limit_headers = {
            "X-RateLimit-Limit": "rate_limit_total",
            "X-RateLimit-Remaining": "rate_limit_remaining",
            "X-RateLimit-Reset": "rate_limit_reset",
            "Retry-After": "retry_after",
        }

        for header, key in rate_limit_headers.items():
            if header in response.headers:
                log_data[key] = response.headers[header]

        # Log as structured JSON for easy parsing
        logging.debug(f"API_USAGE: {json.dumps(log_data)}")

        # Warn if approaching rate limits
        if "rate_limit_remaining" in log_data:
            remaining = int(log_data["rate_limit_remaining"])
            if remaining < 10:
                logging.warning(
                    f"{self.api_name} API: Only {remaining} requests remaining in current period!"
                )

    def set_lastpage(self, lastpage):
        self.lastpage = lastpage

    def createCollectDir(self):
        if not os.path.isdir(self.get_apiDir()):
            os.makedirs(self.get_apiDir())
        if not os.path.isdir(self.get_collectDir()):
            os.makedirs(self.get_collectDir())

    def get_collectId(self):
        return self.collectId

    def set_collectId(self, collectId):
        self.collectId = collectId

    def set_state(self, complete):
        self.state = complete

    def savePageResults(self, global_data, page):
        """
        Save page results with buffering.
        Results are buffered and written in batches to reduce I/O overhead.
        """
        # Add to buffer
        self._result_buffer.append((page, global_data))

        # Flush buffer if it reaches the batch size
        if len(self._result_buffer) >= self._buffer_size:
            self._flush_buffer()

    def _flush_buffer(self):
        """Write buffered results to disk."""
        if not self._result_buffer:
            return

        self.createCollectDir()
        logging.debug(
            f"Flushing {len(self._result_buffer)} pages to {self.get_collectDir()}"
        )

        for page, global_data in self._result_buffer:
            with open(
                self.get_collectDir() + "/page_" + str(page), "w", encoding="utf8"
            ) as json_file:
                json.dump(global_data, json_file)

        self._result_buffer.clear()

    def get_lastpage(self):
        return self.lastpage

    def get_api_name(self):
        return self.api_name

    def get_keywords(self):
        return self.filter_param.get_keywords()

    def get_year(self):
        return self.filter_param.get_year()

    def get_dataDir(self):
        return self.datadir

    def get_apiDir(self):
        return self.get_dataDir() + "/" + self.get_api_name()

    def get_collectDir(self):
        return self.get_apiDir() + "/" + str(self.get_collectId())

    def get_fileCollect(self):
        return self.get_dataDir() + "/collect_dict.json"

    def get_url(self):
        return self.api_url

    def get_apikey(self):
        return self.api_key

    def get_max_by_page(self):
        return self.max_by_page

    def get_ratelimit(self):
        return self.rate_limit

    def _get_auth_recovery_actions(self, status_code):
        """
        Get specific recovery actions for authentication errors based on API and status code.

        Args:
            status_code: HTTP status code (401 or 403)

        Returns:
            str: Formatted recovery actions for the user
        """
        actions = []

        if status_code == 401:
            actions.append(
                "1. Check that your API key is correctly configured in api.config.yml"
            )
            actions.append(
                f"2. Verify the API key for {self.api_name} is valid and not expired"
            )
        elif status_code == 403:
            actions.append("1. Verify your API key has the necessary permissions")
            actions.append("2. Check if your IP address needs to be whitelisted")

            # API-specific guidance
            if self.api_name == "Elsevier":
                actions.append(
                    "3. Elsevier-specific: Verify both 'api_key' and 'inst_token' in api.config.yml"
                )
                actions.append(
                    "4. Elsevier-specific: Check if you need institutional access (inst_token)"
                )
                actions.append(
                    "5. Elsevier-specific: Verify your API key tier allows Scopus access"
                )
            elif self.api_name == "IEEE":
                actions.append(
                    "3. IEEE-specific: Check your API key quota (200 requests/day limit)"
                )
                actions.append(
                    "4. IEEE-specific: Visit https://developer.ieee.org/ to verify key status"
                )
            elif self.api_name == "Springer":
                actions.append(
                    "3. Springer-specific: Check your subscription tier and rate limits"
                )

        actions.append(
            f"\nFor help, check: src/api.config.yml.example for {self.api_name} configuration"
        )
        return "\n   ".join(actions)

    @staticmethod
    def _sanitize_url(url):
        """
        Remove sensitive information (API keys, tokens) from URLs for logging.

        Args:
            url: URL string that may contain sensitive parameters

        Returns:
            str: Sanitized URL with sensitive parameters masked
        """
        import re

        # Replace API keys in query parameters
        url = re.sub(r"([?&]api[Kk]ey=)[^&]+", r"\1***REDACTED***", url)
        url = re.sub(r"([?&]apikey=)[^&]+", r"\1***REDACTED***", url)
        url = re.sub(r"([?&]key=)[^&]+", r"\1***REDACTED***", url)
        url = re.sub(r"([?&]token=)[^&]+", r"\1***REDACTED***", url)
        return url

    def api_call_decorator(
        self,
        configurated_url,
        max_retries=CircuitBreakerConfig.MAX_RETRIES,
        headers=None,
    ):
        """
        API call decorator with circuit breaker, retry logic, and error handling.

        Args:
            configurated_url: The URL to call
            max_retries: Maximum number of retry attempts (default: 3)
            headers: Optional dict of HTTP headers to include in the request

        Returns:
            Response object from the API

        Raises:
            CircuitBreakerOpenError: If circuit breaker is open (API endpoint failing repeatedly)
        """
        logging.debug(f"API Request to: {configurated_url}")

        # Get circuit breaker for this API
        registry = CircuitBreakerRegistry()
        breaker = registry.get_breaker(
            api_name=self.api_name,
            failure_threshold=CircuitBreakerConfig.FAILURE_THRESHOLD,
            timeout_seconds=CircuitBreakerConfig.TIMEOUT_SECONDS,
        )

        # Check circuit breaker state
        if not breaker.is_available():
            # Circuit is OPEN, fail fast without trying
            logging.error(
                f"{self.api_name} API: Circuit breaker OPEN - skipping request to save time"
            )
            raise CircuitBreakerOpenError(self.api_name, breaker.timeout_seconds)

        @sleep_and_retry
        @limits(calls=self.get_ratelimit(), period=1)
        def access_rate_limited_decorated(configurated_url):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    resp = self.session.get(
                        configurated_url, headers=headers, timeout=30
                    )
                    resp.raise_for_status()

                    # Log successful request with rate limit info
                    logging.debug(
                        f"{self.api_name} API: Request successful (attempt {attempt + 1}/{max_retries})"
                    )

                    # Record success in circuit breaker
                    breaker.record_success()

                    return resp

                except requests.exceptions.HTTPError as e:
                    status_code = e.response.status_code
                    last_exception = e

                    if status_code == 429:  # Too Many Requests
                        # Get API-specific backoff configuration
                        base_wait, use_exponential = (
                            RateLimitBackoffConfig.API_SPECIFIC.get(
                                self.api_name,
                                (
                                    RateLimitBackoffConfig.DEFAULT_BASE_WAIT,
                                    RateLimitBackoffConfig.DEFAULT_USE_EXPONENTIAL,
                                ),
                            )
                        )

                        # Calculate wait time based on strategy
                        if use_exponential:
                            wait_time = base_wait * (2**attempt)  # Exponential backoff
                        else:
                            wait_time = base_wait  # Fixed wait time

                        logging.warning(
                            f"{self.api_name} API rate limit exceeded (429). "
                            f"Waiting {wait_time}s before retry (attempt {attempt + 1}/{max_retries}). "
                            f"Strategy: {'exponential' if use_exponential else 'fixed'} backoff"
                        )
                        if attempt < max_retries - 1:
                            time.sleep(wait_time)
                            continue
                        else:
                            # Final retry failed - don't record as circuit breaker failure
                            # Rate limits are temporary and don't indicate endpoint failure
                            logging.warning(
                                f"{self.api_name} API: Rate limit persists after {max_retries} retries with {wait_time}s waits. "
                                f"Consider reducing rate_limit in api.config.yml or increasing backoff time."
                            )
                            raise  # Re-raise to let caller handle
                    elif status_code in [401, 403]:  # Authentication errors
                        # Build specific recovery guidance based on API
                        recovery_actions = self._get_auth_recovery_actions(status_code)

                        logging.error(
                            f"{self.api_name} API authentication failed: {status_code}. "
                            f"Recovery actions:\n{recovery_actions}"
                        )
                        # Record failure for circuit breaker
                        breaker.record_failure()
                        raise  # Don't retry auth errors
                    elif status_code == 500:  # Internal server error
                        wait_time = 2**attempt
                        logging.warning(
                            f"{self.api_name} API internal server error (500). "
                            f"This may indicate API overload or rate limiting. "
                            f"Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                        )
                        if attempt < max_retries - 1:
                            time.sleep(wait_time)
                            breaker.record_failure()  # Track failure for circuit breaker
                            continue
                        else:
                            logging.error(
                                f"{self.api_name} API: 500 errors persisting after {max_retries} retries. "
                                f"Consider checking API status or reducing concurrency."
                            )
                            breaker.record_failure()
                            raise
                    elif status_code in [502, 503, 504]:  # Gateway/service errors
                        wait_time = 2**attempt
                        logging.warning(
                            f"{self.api_name} API gateway/service error ({status_code}). "
                            f"Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                        )
                        if attempt < max_retries - 1:
                            time.sleep(wait_time)
                            breaker.record_failure()  # Track failure for circuit breaker
                            continue
                        else:
                            breaker.record_failure()
                            raise
                    elif status_code >= 500:  # Other 5xx errors
                        wait_time = 2**attempt
                        logging.warning(
                            f"{self.api_name} API server error: {status_code}. "
                            f"Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                        )
                        if attempt < max_retries - 1:
                            time.sleep(wait_time)
                            breaker.record_failure()  # Track failure for circuit breaker
                            continue
                        else:
                            breaker.record_failure()
                            raise
                    else:
                        logging.error(
                            f"{self.api_name} API HTTP error {status_code}: {str(e)}"
                        )
                        # Record failure for circuit breaker
                        breaker.record_failure()
                        raise

                except requests.exceptions.Timeout as e:
                    last_exception = e
                    wait_time = 2**attempt
                    logging.warning(
                        f"{self.api_name} API request timeout. "
                        f"Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
                        continue
                    else:
                        logging.error(
                            f"{self.api_name} API: All retry attempts failed due to timeout"
                        )
                        # Record failure for circuit breaker
                        breaker.record_failure()
                        raise

                except requests.exceptions.ConnectionError as e:
                    last_exception = e
                    wait_time = 2**attempt
                    logging.warning(
                        f"{self.api_name} API connection error. "
                        f"Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
                        continue
                    else:
                        logging.error(
                            f"{self.api_name} API: All retry attempts failed due to connection error"
                        )
                        # Record failure for circuit breaker
                        breaker.record_failure()
                        raise

                except requests.exceptions.RequestException as e:
                    last_exception = e
                    logging.error(
                        f"{self.api_name} API request failed: {str(e)}. "
                        f"Attempt {attempt + 1}/{max_retries}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(2**attempt)
                        continue
                    else:
                        # Record failure for circuit breaker
                        breaker.record_failure()
                        raise

            # If we exhausted all retries, raise the last exception
            if last_exception:
                logging.error(
                    f"{self.api_name} API: All {max_retries} retry attempts exhausted"
                )
                # Record failure for circuit breaker
                breaker.record_failure()
                raise last_exception

        return access_rate_limited_decorated(configurated_url)

    def toZotero():
        pass

    def runCollect(self):
        """
        Runs the collection process for DBLP and Springer publications.

        This method retrieves publication data in pages until all results
        are collected or a specified limit is reached.
        """

        state_data = {
            "state": self.state,
            "last_page": self.lastpage,
            "total_art": self.total_art,
            "coll_art": self.nb_art_collected,
            "update_date": str(date.today()),
            "id_collect": self.collectId,
        }
        # self.getCollectId()  # Retrieve the collection identifier

        # Check if the collection has already been completed
        if self.state == 1:
            logging.info("Collection already completed.")
            return  # Exit if collection is complete

        page = int(self.get_lastpage()) + 1  # Start from the next page
        has_more_pages = True
        logging.debug(f"Starting collection from page {page}")
        # Determine if there are fewer than 10,000 results based on collection size
        fewer_than_10k_results = self.big_collect == 0

        # Import here to avoid circular imports
        from .arxiv import Arxiv_collector
        from .springer import Springer_collector

        if isinstance(self, Springer_collector):
            # If this is a Springer collector, use the 'collect_from_endpoints' method
            logging.info("Running collection for Springer data.")

            try:
                combined_results = (
                    self.collect_from_endpoints()
                )  # Collect results from Springer endpoints

                for page_data in combined_results:
                    # PRE-CHECK: Stop if we've already collected enough articles
                    max_articles = self.filter_param.get_max_articles_per_query()
                    if max_articles > 0 and self.nb_art_collected >= max_articles:
                        logging.info(
                            f"Reached max_articles_per_query limit ({max_articles}). "
                            f"Already collected {self.nb_art_collected} articles. Skipping remaining pages."
                        )
                        break

                    # Save each page's results
                    self.savePageResults(page_data, page)
                    self.nb_art_collected += len(page_data["results"])

                    # Update the last page collected
                    self.set_lastpage(int(page) + 1)

                    # Check if more pages are available based on results
                    if (
                        len(page_data["results"]) > 0
                        and "total" in page_data
                        and page_data["total"] > 0
                    ):
                        # Calculate expected pages based on total results
                        expected_pages = math.ceil(
                            page_data["total"] / self.get_max_by_page()
                        )
                        has_more_pages = page < expected_pages

                        # Check if we've collected enough articles
                        max_articles = self.filter_param.get_max_articles_per_query()
                        if max_articles > 0 and self.nb_art_collected >= max_articles:
                            logging.debug(
                                f"Collected {self.nb_art_collected} articles (limit: {max_articles}). "
                                f"No more pages needed."
                            )
                            has_more_pages = False
                    else:
                        has_more_pages = False

                    page = self.get_lastpage()  # Update the current page number

                    # Check if total results are within the limit
                    fewer_than_10k_results = page_data["total"] <= 10000
                    logging.debug(
                        f"Processed page {page}: {len(page_data['results'])} results. Total found: {page_data['total']}"
                    )

            except Exception as e:
                # Log additional context about the error
                logging.error(
                    f"Error processing results on page {page} from Springer API: {str(e)}"
                )
                has_more_pages = False  # Stop collecting if there's an error

        else:
            # If this is a DBLP collector, follow the normal process

            while has_more_pages and fewer_than_10k_results:
                # PRE-CHECK: Stop if we've already collected enough articles
                max_articles = self.filter_param.get_max_articles_per_query()
                if max_articles > 0 and self.nb_art_collected >= max_articles:
                    logging.info(
                        f"Reached max_articles_per_query limit ({max_articles}). "
                        f"Already collected {self.nb_art_collected} articles. Stopping before page {page}."
                    )
                    break

                offset = self.get_offset(page)  # Calculate the current offset

                url = self.get_configurated_url().format(
                    offset
                )  # Construct the API URL

                logging.debug(f"Fetching data from URL: {url}")

                response = self.api_call_decorator(url)  # Call the API
                logging.debug(f"{self.api_name} API call completed for page {page}")
                try:
                    page_data = self.parsePageResults(
                        response, page
                    )  # Parse the response

                    # Log API usage statistics
                    self.log_api_usage(
                        response, page, len(page_data.get("results", []))
                    )

                    self.nb_art_collected += int(len(page_data["results"]))
                    nb_res = len(page_data["results"])

                    # Determine if more pages are available based on results returned
                    if nb_res != 0 and "total" in page_data and page_data["total"] > 0:
                        # Calculate expected pages based on total results
                        expected_pages = math.ceil(
                            page_data["total"] / self.get_max_by_page()
                        )

                        # Check if we should fetch more pages based on total
                        has_more_pages = page < expected_pages

                        # Check if we've collected enough articles
                        max_articles = self.filter_param.get_max_articles_per_query()
                        if max_articles > 0 and self.nb_art_collected >= max_articles:
                            logging.debug(
                                f"Collected {self.nb_art_collected} articles (limit: {max_articles}). "
                                f"No more pages needed."
                            )
                            has_more_pages = False
                    else:
                        has_more_pages = False

                    if isinstance(self, Arxiv_collector):
                        page_data["results"] = [
                            x for x in page_data["results"] if x is not None
                        ]
                    logging.debug(f"Articles collected so far: {self.nb_art_collected}")
                    # Save the page results for future use
                    self.savePageResults(page_data, page)
                    # Update the last page collected
                    self.set_lastpage(int(page) + 1)

                    # print("MAX ART >", self.get_max_by_page())
                    page = self.get_lastpage()  # Update the current page number

                    state_data["last_page"] = page
                    state_data["total_art"] = page_data["total"]
                    state_data["coll_art"] = state_data["coll_art"] + len(
                        page_data["results"]
                    )

                    # Check if the total number of results is within the limit
                    # fewer_than_10k_results = page_data["total"] <= 10000

                    logging.debug(
                        f"Processed page {page}: {len(page_data['results'])} results. Total found: {page_data['total']}"
                    )

                except Exception as e:
                    # Log additional context about the error
                    logging.error(
                        f"Error processing results on page {page} from URL '{url}': {str(e)}. "
                        f"Response type: {type(response)}."
                    )
                    has_more_pages = False  # Stop collecting if there's an error
                    state_data["state"] = 0
                    state_data["last_page"] = page
                    self._flush_buffer()  # Flush before early return (Phase 1)
                    return state_data

        # Final log messages based on the collection status

        if not has_more_pages:
            logging.debug("No more pages to collect. Marking collection as complete.")
            # self.flagAsComplete()
            state_data["state"] = 1
        else:
            time_needed = page_data["total"] / self.get_max_by_page() / 60 / 60
            logging.info(
                f"Total extraction will need approximately {time_needed:.2f} hours."
            )

        # Flush any remaining buffered results
        self._flush_buffer()

        return state_data

    def add_offset_param(self, page):
        return self.get_configurated_url().format((page - 1) * self.get_max_by_page())

    def get_offset(self, page):
        return (page - 1) * self.get_max_by_page()
