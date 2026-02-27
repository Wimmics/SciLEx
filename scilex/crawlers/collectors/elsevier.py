import logging
from datetime import date

from scilex.constants import CircuitBreakerConfig

from .base import API_collector


class Elsevier_collector(API_collector):
    """Store file metadata from Elsevier API."""

    def __init__(self, filter_param, data_path, api_key, inst_token=None):
        """
        Initialize Elsevier Scopus API collector.

        Args:
            filter_param: Filter parameters for the search
            data_path: Path for saving data
            api_key: Elsevier API key (required)
            inst_token: Institutional token for enhanced access (optional but recommended)
        """
        super().__init__(filter_param, data_path, api_key)
        self.max_by_page = 25  # Scopus API max is 25 per page
        self.api_name = "Elsevier"
        self.api_url = "https://api.elsevier.com/content/search/scopus"
        self.inst_token = inst_token
        self.load_rate_limit_from_config()
        if self.inst_token:
            logging.debug(
                "Initialized Elsevier collector WITH institutional token (enhanced access)"
            )
        else:
            logging.debug(
                "Initialized Elsevier collector WITHOUT institutional token (standard access)"
            )

    def api_call_decorator(
        self, configurated_url, max_retries=CircuitBreakerConfig.MAX_RETRIES
    ):
        """
        API call with Elsevier-specific headers and optional institutional token.
        Calls parent decorator with circuit breaker and retry logic.

        Args:
            configurated_url: The URL to call
            max_retries: Maximum number of retry attempts (default from CircuitBreakerConfig)

        Returns:
            Response object from the API
        """
        headers = {"X-ELS-APIKey": self.get_apikey(), "Accept": "application/json"}

        # Add institutional token if available (provides better access)
        if self.inst_token:
            headers["X-ELS-Insttoken"] = self.inst_token
            logging.debug("Using institutional token for Elsevier API request")

        return super().api_call_decorator(
            configurated_url, max_retries=max_retries, headers=headers
        )

    def parsePageResults(self, response, page):
        """Parse the JSON response from Elsevier API and return structured data."""
        page_data = {
            "date_search": str(date.today()),
            "id_collect": self.get_collectId(),
            "page": page,
            "total": 0,
            "results": [],
        }

        page_with_results = response.json()

        # Loop through partial list of results
        results = page_with_results["search-results"]
        total = results["opensearch:totalResults"]
        page_data["total_nb"] = int(total)
        if page_data["total_nb"] > 0:
            for result in results["entry"]:
                page_data["results"].append(result)

        return page_data

    def construct_search_query(self):
        """
        Constructs a search query for the API from the keyword sets.
        The format will be:
        TITLE(NLP OR Natural Language Processing) AND TITLE(Pragmatic OR Pragmatics)
        """
        # formatted_keyword_groups = []

        # Iterate through each set of keywords
        # for keyword_set in self.get_keywords():
        # Initialize a list to hold the formatted keywords for the current group
        #  group_keywords = []

        # Join keywords within the same set with ' OR '
        # group_keywords += [f'"{keyword}"' for keyword in keyword_set]  # Use quotes for exact matching

        # Join the current group's keywords with ' OR ' and wrap in TITLE()

        search_query = f"TITLE-ABS({' AND '.join(self.get_keywords())})"

        # Join all formatted keyword groups with ' AND '
        # search_query = ' AND '.join(formatted_keyword_groups)

        return search_query

    def get_configurated_url(self):
        """Constructs the API URL with the search query and publication year filters."""
        # Construct the search query
        keywords_query = (
            self.construct_search_query()
        )  # Get the formatted keyword query

        # Create the years query
        years_query = self.get_year()
        # Combine the queries
        query = f"{keywords_query}&date={years_query}"

        return f"{self.api_url}?query={query}&apiKey={self.api_key}&count={self.max_by_page}&start={{}}"
