import logging
from datetime import date

from .base import API_collector


class OpenAlex_collector(API_collector):
    """Class to collect publication data from the OpenAlex API."""

    def __init__(self, filter_param, data_path, api_key):
        """Initialize the OpenAlex collector with the given parameters.

        Args:
            filter_param (Filter_param): The parameters for filtering results (years, keywords, etc.).
            data_path (str): Path to save the collected data.
            api_key: API key from api.config.yml (free, get at openalex.org/settings/api).
                Without key: 100 credits/day. With key: 100,000 credits/day.
        """
        super().__init__(filter_param, data_path, api_key)
        self.max_by_page = 200  # Maximum number of results to retrieve per page
        self.api_name = "OpenAlex"
        self.api_url = "https://api.openalex.org/works"
        self.load_rate_limit_from_config()

    def parsePageResults(self, response, page):
        """Parse the results from a response for a specific page.

        Args:
            response (requests.Response): The API response object containing the results.
            page (int): The page number of results being processed.

        Returns:
            tuple: A (page_data dict, next_cursor str or None) pair.
                page_data contains metadata about the collected results.
                next_cursor is the cursor for the next page, or None if no more pages.
        """
        page_data = {
            "date_search": str(date.today()),
            "id_collect": self.get_collectId(),
            "page": page,
            "total": 0,
            "results": [],
        }

        page_with_results = response.json()

        meta = page_with_results.get("meta", {})
        total = meta.get("count", 0)
        page_data["total"] = int(total)
        next_cursor = meta.get("next_cursor")
        logging.debug(f"Total results found for page {page}: {page_data['total']}")

        if page_data["total"] > 0:
            for result in page_with_results.get("results", []):
                page_data["results"].append(result)

        return page_data, next_cursor

    def get_configurated_url(self):
        """Construct the API URL with search query and filters.

        Returns a base URL without pagination parameters — cursor pagination
        is appended by runCollect().

        Returns:
            str: The formatted API URL for the request.
        """
        keyword_filters = []

        for keyword_set in self.get_keywords():
            # Use title_and_abstract.search to search both title AND abstract
            keyword_filters.append(f"title_and_abstract.search:{keyword_set}")

        formatted_keyword_filters = ",".join(keyword_filters)

        years = self.get_year()
        year_filter = f"publication_year:{years}"

        # Base URL without pagination — cursor is appended in runCollect()
        api_url = (
            f"{self.api_url}?filter={formatted_keyword_filters},{year_filter}"
            f"&per-page={self.max_by_page}"
        )

        # Add API key if configured (free key: 100k credits/day vs 100 without)
        if self.api_key:
            api_url += f"&api_key={self.api_key}"

        logging.debug(f"Configured URL: {self._sanitize_url(api_url)}")
        return api_url

    def runCollect(self):
        """Run collection using OpenAlex cursor-based pagination.

        Cursor pagination has no 10k result limit (unlike page-based pagination).
        See: https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/paging#cursor-paging
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

        base_url = self.get_configurated_url()
        cursor = "*"  # Initial cursor value for first request
        page = int(self.get_lastpage()) + 1

        logging.debug(f"Starting OpenAlex cursor-based collection from page {page}")

        while cursor is not None:
            # Check max articles limit before fetching
            max_articles = self.filter_param.get_max_articles_per_query()
            if max_articles > 0 and self.nb_art_collected >= max_articles:
                logging.info(
                    f"Reached max_articles_per_query limit ({max_articles}). "
                    f"Already collected {self.nb_art_collected} articles. Stopping."
                )
                break

            url = f"{base_url}&cursor={cursor}"
            logging.debug(f"Fetching data from URL: {self._sanitize_url(url)}")

            try:
                response = self.api_call_decorator(url)
                logging.debug(f"OpenAlex API call completed for page {page}")

                page_data, next_cursor = self.parsePageResults(response, page)

                # Log API usage statistics
                self.log_api_usage(response, page, len(page_data.get("results", [])))

                nb_results = len(page_data["results"])
                self.nb_art_collected += nb_results

                if nb_results == 0:
                    logging.debug("No more results returned. Collection complete.")
                    break

                self.savePageResults(page_data, page)
                self.set_lastpage(int(page) + 1)
                page = self.get_lastpage()

                state_data["last_page"] = page
                state_data["total_art"] = page_data["total"]
                state_data["coll_art"] = state_data["coll_art"] + nb_results

                logging.debug(
                    f"Processed page {page - 1}: {nb_results} results. "
                    f"Total found: {page_data['total']}. "
                    f"Collected so far: {self.nb_art_collected}"
                )

                # Advance cursor
                cursor = next_cursor

            except Exception as e:
                logging.error(
                    f"Error processing results on page {page} from OpenAlex API: {e}"
                )
                state_data["state"] = 0
                state_data["last_page"] = page
                self._flush_buffer()
                return state_data

        # Collection complete
        logging.debug("OpenAlex collection complete. Marking as done.")
        state_data["state"] = 1
        self._flush_buffer()
        return state_data
