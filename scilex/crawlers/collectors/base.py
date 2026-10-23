import json
import logging
import math
import os
import time
from datetime import date

import requests

from scilex.config_defaults import get_rate_limit
from scilex.constants import CircuitBreakerConfig, RateLimitBackoffConfig
from scilex.crawlers.adaptive_rate_limiter import AdaptiveRateLimiterRegistry
from scilex.crawlers.circuit_breaker import (
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
)
from scilex.crawlers.utils import sanitize_secrets
from scilex.since_utils import parse_since, query_start_date

# Marker files written in each query directory (see CollectCollection._query_is_complete)
COMPLETE_FILE_NAME = "_complete"  # query fully collected
STATE_FILE_NAME = "_state"  # query started but not finished


class Filter_param:
    def __init__(self, year, keywords, max_articles_per_query=-1, since=None):
        # Initialize the parameters
        self.year = year
        # Keywords is now a list of lists to support multiple sets
        self.keywords = keywords
        # Maximum articles per query (-1 = unlimited)
        self.max_articles_per_query = max_articles_per_query
        # Optional lower bound date (ISO string) for incremental re-collection
        self.since = since

    def get_dict_param(self):
        # Return the instance's dictionary representation
        return self.__dict__

    def get_year(self):
        return self.year

    def get_keywords(self):
        return self.keywords

    def get_since(self):
        return parse_since(self.since)

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
            data_query.get("since"),
        )
        self.rate_limit = 10  # Will be overridden by load_rate_limit_from_config()
        self.datadir = data_path
        self.collectId = data_query["id_collect"]
        self.total_art = int(data_query["total_art"])
        self.lastpage = int(data_query["last_page"])
        self.nb_art_collected = int(data_query["coll_art"])
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

    def _rate_limit_wait(self):
        """Enforce per-API rate limit, including inter-query gaps.

        Delegates to the process-wide AdaptiveRateLimiterRegistry so the
        timer persists across collector instances.  The registry also tracks
        adaptive back-off: delay doubles on each persistent 429 and halves
        after sustained success.
        """
        if self.rate_limit <= 0:
            return
        AdaptiveRateLimiterRegistry().get(self.api_name).wait(self.rate_limit)

    def load_rate_limit_from_config(self, rate_limits=None):
        """Set ``self.rate_limit`` for this API (requests per second).

        Args:
            rate_limits: Optional ``rate_limits`` mapping from the user's
                api config (``{api_name: req_per_sec}``). When it contains this
                API, the value wins; otherwise the key-aware defaults from
                ``config_defaults.get_rate_limit`` apply.

        Must be called after ``self.api_name`` is set in the subclass __init__.
        """
        if isinstance(rate_limits, dict) and self.api_name in rate_limits:
            try:
                self.rate_limit = float(rate_limits[self.api_name])
                logging.debug(
                    f"{self.api_name}: Using configured rate limit of {self.rate_limit} req/sec"
                )
                return
            except (TypeError, ValueError):
                logging.warning(
                    f"{self.api_name}: Invalid configured rate limit "
                    f"{rate_limits[self.api_name]!r}. Using default."
                )

        has_key = bool(self.api_key)
        default_limit = get_rate_limit(self.api_name, has_api_key=has_key)
        self.rate_limit = default_limit
        key_status = "with" if has_key else "without"
        logging.debug(
            f"{self.api_name}: Using default rate limit of {default_limit} req/sec ({key_status} API key)"
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
            try:
                remaining = int(log_data["rate_limit_remaining"])
            except (TypeError, ValueError):
                return  # Non-numeric header (some APIs send "n/a" or dates)
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

    def get_query_start_date(self):
        """Return the ``since`` date if it falls in this query's year, else None."""
        return query_start_date(self.get_year(), self.filter_param.get_since())

    def get_dataDir(self):
        return self.datadir

    def get_apiDir(self):
        return self.get_dataDir() + "/" + self.get_api_name()

    def get_collectDir(self):
        return self.get_apiDir() + "/" + str(self.get_collectId())

    def get_url(self):
        return self.api_url

    def get_apikey(self):
        return self.api_key

    def get_max_by_page(self):
        return self.max_by_page

    def get_auth_headers(self):
        """Return HTTP headers for authentication. Override in subclasses that need auth headers."""
        return None

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
        """Mask API keys and tokens in a URL before logging it."""
        return sanitize_secrets(url)

    # HTTP statuses that are retried (409 is treated as a throttle: OpenAIRE
    # answers 409 for parallel scroll contexts).
    THROTTLE_STATUS = frozenset({409, 429})
    RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
    MAX_RETRY_AFTER_SECONDS = 120

    def _retry_wait(self, attempt, response=None):
        """Seconds to wait before retry number ``attempt + 1``.

        Throttle responses honour a numeric ``Retry-After`` header (capped at
        ``MAX_RETRY_AFTER_SECONDS``) and otherwise use the API-specific backoff
        from ``RateLimitBackoffConfig``. Every other error uses ``2**attempt``.
        """
        status_code = getattr(response, "status_code", None)
        if status_code not in self.THROTTLE_STATUS:
            return 2**attempt

        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), self.MAX_RETRY_AFTER_SECONDS)
            except ValueError:
                pass  # HTTP-date or garbage: use the configured backoff

        base_wait, use_exponential = RateLimitBackoffConfig.API_SPECIFIC.get(
            self.api_name,
            (
                RateLimitBackoffConfig.DEFAULT_BASE_WAIT,
                RateLimitBackoffConfig.DEFAULT_USE_EXPONENTIAL,
            ),
        )
        return base_wait * (2**attempt) if use_exponential else base_wait

    def api_call_decorator(
        self,
        configurated_url,
        max_retries=CircuitBreakerConfig.MAX_RETRIES,
        headers=None,
    ):
        """
        API call with circuit breaker, retry logic, and error handling.

        Exactly one circuit-breaker failure is recorded per call that ends in
        an error (after retries are exhausted, or immediately for non-retryable
        errors). Authentication errors (401/403) never trip the breaker.

        Args:
            configurated_url: The URL to call
            max_retries: Maximum number of attempts (default: 3)
            headers: Optional dict of HTTP headers to include in the request

        Returns:
            Response object from the API

        Raises:
            CircuitBreakerOpenError: If circuit breaker is open (API endpoint failing repeatedly)
            requests.exceptions.RequestException: When the call ultimately fails
        """
        logging.debug(f"API Request to: {self._sanitize_url(configurated_url)}")

        breaker = CircuitBreakerRegistry().get_breaker(
            api_name=self.api_name,
            failure_threshold=CircuitBreakerConfig.FAILURE_THRESHOLD,
            timeout_seconds=CircuitBreakerConfig.TIMEOUT_SECONDS,
        )
        if not breaker.is_available():
            logging.error(
                f"{self.api_name} API: Circuit breaker OPEN - skipping request to save time"
            )
            raise CircuitBreakerOpenError(self.api_name, breaker.timeout_seconds)

        max_retries = max(1, max_retries)
        for attempt in range(max_retries):
            is_last_attempt = attempt == max_retries - 1
            response = None
            last_error = None
            try:
                self._rate_limit_wait()
                resp = self.session.get(configurated_url, headers=headers, timeout=30)
                resp.raise_for_status()
                logging.debug(
                    f"{self.api_name} API: Request successful (attempt {attempt + 1}/{max_retries})"
                )
                breaker.record_success()
                AdaptiveRateLimiterRegistry().get(self.api_name).on_success()
                return resp

            except requests.exceptions.HTTPError as e:
                last_error = e
                response = e.response
                status_code = getattr(response, "status_code", None)

                if status_code in (401, 403):
                    # Permanent configuration failure (bad/expired key): do NOT
                    # trip the breaker, it would cascade to every remaining query.
                    logging.error(
                        f"{self.api_name} API authentication failed: {status_code}. "
                        f"Recovery actions:\n{self._get_auth_recovery_actions(status_code)}"
                    )
                    raise

                if status_code not in self.RETRYABLE_STATUS and (
                    status_code not in self.THROTTLE_STATUS
                ):
                    logging.error(
                        f"{self.api_name} API HTTP error {status_code}: {sanitize_secrets(str(e))}"
                    )
                    breaker.record_failure()
                    raise

                error_label = f"HTTP {status_code}"

            except requests.exceptions.RequestException as e:
                # Timeouts, connection errors and other transport failures
                last_error = e
                error_label = type(e).__name__
                logging.debug(
                    f"{self.api_name} API request failed: {sanitize_secrets(str(e))}"
                )

            if is_last_attempt:
                if (
                    response is not None
                    and response.status_code in self.THROTTLE_STATUS
                ):
                    new_delay = (
                        AdaptiveRateLimiterRegistry().get(self.api_name).on_throttle()
                    )
                    logging.warning(
                        f"{self.api_name} API: Throttle ({response.status_code}) persists after "
                        f"{max_retries} attempts. Inter-request delay increased to +{new_delay:.0f}s."
                    )
                logging.error(
                    f"{self.api_name} API: all {max_retries} attempts failed ({error_label})"
                )
                breaker.record_failure()
                raise last_error

            wait_time = self._retry_wait(attempt, response)
            logging.warning(
                f"{self.api_name} API {error_label}. "
                f"Retrying in {wait_time:.0f}s (attempt {attempt + 1}/{max_retries})"
            )
            time.sleep(wait_time)

    def _get_api_endpoints(self):
        """URL templates to paginate through, in order (each has one ``{}`` offset slot).

        Most APIs have a single endpoint. Override for APIs that must be queried
        on several endpoints (e.g. Springer meta + openaccess); pages of all
        endpoints are saved under consecutive page numbers.
        """
        return [self.get_configurated_url()]

    def _post_process_page(self, page_data):
        """Hook to clean a parsed page before it is counted and saved.

        The pagination decision still uses the raw result count of the page.
        """
        return page_data

    def _mark_incomplete(self):
        """Record that a collection run started in this query directory."""
        self.createCollectDir()
        marker = os.path.join(self.get_collectDir(), STATE_FILE_NAME)
        with open(marker, "w") as marker_file:
            marker_file.write("incomplete")

    def _mark_complete(self):
        """Write the completion marker consumed by ``CollectCollection``."""
        self.createCollectDir()
        collect_dir = self.get_collectDir()
        with open(os.path.join(collect_dir, COMPLETE_FILE_NAME), "w") as marker_file:
            marker_file.write("1")
        state_file = os.path.join(collect_dir, STATE_FILE_NAME)
        if os.path.exists(state_file):
            os.remove(state_file)

    @staticmethod
    def _throttle_status(exc):
        """Return 429/409 when ``exc`` is a persistent throttle error, else None."""
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        return status_code if status_code in API_collector.THROTTLE_STATUS else None

    def _try_vpn_rotation(self, throttle_code, page):
        """Rotate the VPN IP after a persistent throttle. True when a retry is worthwhile."""
        from scilex.vpn.rotator import get_vpn_rotator

        rotator = get_vpn_rotator()
        if not rotator.should_rotate(self.api_name):
            return False
        logging.warning(
            f"[VPN] {self.api_name} Q{self.collectId} page {page}: "
            f"persistent {throttle_code} — triggering IP rotation "
            f"(rotation {rotator.rotation_count + 1}/{rotator.max_rotations})"
        )
        if rotator.rotate():
            logging.warning(
                f"[VPN] {self.api_name} Q{self.collectId}: retrying page {page} with new IP"
            )
            return True
        logging.warning(
            f"[VPN] {self.api_name} Q{self.collectId}: "
            f"rotation failed — giving up on this query"
        )
        return False

    def _max_articles_reached(self):
        max_articles = self.filter_param.get_max_articles_per_query()
        return max_articles > 0 and self.nb_art_collected >= max_articles

    def runCollect(self):
        """Collect every page of the query and save them to disk.

        Pages are fetched until the API reports no more results or
        ``max_articles_per_query`` is reached (both mean the query is done,
        ``state`` = 1). Any failure leaves ``state`` = 0 so the query is resumed
        on the next run. Buffered pages are always flushed to disk, even when
        the loop ends on an exception.

        Returns:
            dict: ``state``, ``last_page``, ``total_art``, ``coll_art``,
            ``update_date`` and ``id_collect``.
        """
        state_data = {
            "state": self.state,
            "last_page": self.lastpage,
            "total_art": self.total_art,
            "coll_art": self.nb_art_collected,
            "update_date": str(date.today()),
            "id_collect": self.collectId,
        }

        if self.state == 1:
            logging.info("Collection already completed.")
            return state_data

        endpoints = self._get_api_endpoints()
        if len(endpoints) > 1 and self.lastpage > 0:
            # Pages of several endpoints share one numbering, so a partial run
            # cannot be resumed mid-way: start over (page files are overwritten).
            logging.info(
                f"{self.api_name} Q{self.collectId}: restarting multi-endpoint "
                f"collection from scratch"
            )
            self.set_lastpage(0)
            self.nb_art_collected = 0
            state_data["last_page"] = 0
            state_data["coll_art"] = 0

        self._mark_incomplete()
        completed = False
        try:
            completed = all(
                self._collect_endpoint(endpoint, state_data, resume=len(endpoints) == 1)
                for endpoint in endpoints
            )
        finally:
            self._flush_buffer()

        if completed:
            logging.debug("No more pages to collect. Marking collection as complete.")
            state_data["state"] = 1
            self._mark_complete()
        return state_data

    def _collect_endpoint(self, endpoint_url, state_data, resume):
        """Paginate through one endpoint. Return True when it was fully collected."""
        endpoint_page = self.get_lastpage() + 1 if resume else 1
        first_results_logged = False

        while True:
            if self._max_articles_reached():
                logging.info(
                    f"Reached max_articles_per_query limit "
                    f"({self.filter_param.get_max_articles_per_query()}). "
                    f"Already collected {self.nb_art_collected} articles. Stopping."
                )
                return True

            page = self.get_lastpage() + 1  # Page file number (1-based)
            url = endpoint_url.format(self.get_offset(endpoint_page))
            logging.debug(f"Fetching data from URL: {self._sanitize_url(url)}")

            try:
                response = self.api_call_decorator(url, headers=self.get_auth_headers())
            except Exception as api_exc:
                throttle_code = self._throttle_status(api_exc)
                if throttle_code and self._try_vpn_rotation(throttle_code, page):
                    continue  # Same page, new IP
                logging.error(
                    f"{self.api_name} API call failed for page {page} "
                    f"(query {self.collectId}): {sanitize_secrets(api_exc)}. "
                    f"The query stays incomplete and will be resumed on the next run."
                )
                return False

            try:
                page_data = self.parsePageResults(response, page)
                self.log_api_usage(response, page, len(page_data.get("results", [])))
                raw_count = len(page_data["results"])
                page_data = self._post_process_page(page_data)
                nb_results = len(page_data["results"])
                total = page_data["total"]
            except Exception as parse_exc:
                logging.error(
                    f"Error processing results on page {page} from "
                    f"{self.api_name} (query {self.collectId}): "
                    f"{sanitize_secrets(parse_exc)}. Response type: {type(response)}."
                )
                return False

            self.nb_art_collected += nb_results
            if not first_results_logged and nb_results > 0:
                kw_str = " + ".join(f'"{k}"' for k in self.get_keywords())
                logging.info(
                    f"[{self.api_name}] Q{self.collectId} ({kw_str}, {self.get_year()}): "
                    f"page {page} → {nb_results} results, {total} total"
                )
                first_results_logged = True

            has_more_pages = (
                raw_count != 0
                and total > 0
                and endpoint_page < math.ceil(total / self.get_max_by_page())
            )

            self.savePageResults(page_data, page)
            self.set_lastpage(page)
            endpoint_page += 1

            state_data["last_page"] = page
            state_data["total_art"] = total
            state_data["coll_art"] = self.nb_art_collected
            logging.debug(
                f"Processed page {page}: {nb_results} results. Total found: {total}. "
                f"Collected so far: {self.nb_art_collected}"
            )

            if not has_more_pages:
                return True

    def get_offset(self, page):
        return (page - 1) * self.get_max_by_page()
