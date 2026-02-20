import logging
import math
from datetime import date

from .base import API_collector


class Springer_collector(API_collector):
    """Store file metadata from Springer API."""

    def __init__(self, filter_param, data_path, api_key):
        """
        Initialize the Springer Collector.

        Args:
            filter_param (dict): The filter parameters for the search query.
            data_path (str): Path to save the data.
        """
        super().__init__(filter_param, data_path, api_key)
        self.api_name = "Springer"
        self.max_by_page = 100
        #     self.api_key = springer_api
        ## manage both meta and openaccess endpoints
        if isinstance(self.api_key, dict):
            self.meta_api_key = self.api_key.get("meta_api_key")
            self.openaccess_api_key = self.api_key.get("openaccess_api_key")
        else:
            self.meta_api_key = self.api_key
            self.openaccess_api_key = self.api_key

        # Define both API URLs
        self.meta_url = "http://api.springernature.com/meta/v2/json"
        self.openaccess_url = "http://api.springernature.com/openaccess/json"

        # Load rate limit from config (defaults to 1.5 req/sec for Basic tier)
        self.load_rate_limit_from_config()

    def parsePageResults(self, response, page):
        """
        Parses the JSON response from the API for a specific page of results.

        Args:
            response (requests.Response): The response object from the API call.
            page (int): The current page number being processed.

        Returns:
            dict: A dictionary containing metadata about the search, including
                the date of search, collection ID, current page, total results,
                and the parsed results.
        """
        # Initialize the dictionary to hold the parsed page data
        page_data = {
            "date_search": str(date.today()),
            "id_collect": self.get_collectId(),
            "page": page,
            "total": 0,
            "results": [],
        }

        try:
            # Parse the JSON response from the API
            page_with_results = response.json()

            # Extract the 'records' list and the 'result' which contains metadata
            records = page_with_results.get("records", [])
            result_info = page_with_results.get("result", [])

            # Handle 'result' being a list and extract the first entry's 'total' if available
            if isinstance(result_info, list) and len(result_info) > 0:
                total = result_info[0].get("total", 0)
            else:
                total = 0

            page_data["total_nb"] = int(total)

            # Process the 'records' if they exist and are in the correct format
            if isinstance(records, list) and len(records) > 0:
                for result in records:
                    page_data["results"].append(result)
            else:
                logging.warning(
                    f"No valid records found on page {page}. Records type: {type(records)}. Response: {page_with_results}"
                )

        except Exception as e:
            # Log detailed error information
            logging.error(
                f"Error parsing page {page}. Response content: {response.text}. Error: {str(e)}"
            )
            raise

        return page_data

    def construct_search_query(self):
        """
        Constructs a search query for the Springer API from the keyword sets.
        The format will be:
        (title:"keyword1" OR title:"keyword2") AND (title:"keyword3" OR title:"keyword4")
        """
        # formatted_keyword_groups = []

        # Iterate through each set of keywords
        # for keyword_set in self.get_keywords():
        # Join keywords within the same set with ' OR ' and format for title
        #   group_keywords = ' OR '.join([f'"{keyword}"' for keyword in keyword_set])
        #  formatted_keyword_groups.append(f"({group_keywords})")

        # Join all formatted keyword groups with ' AND '
        search_query = " AND ".join([f'"{keyword}"' for keyword in self.get_keywords()])
        return search_query

    def get_configurated_url(self):
        """
        Constructs the URLs for both API endpoints.

        Returns:
            list: A list of constructed API URLs for both endpoints.
        """
        # Construct the search query
        keywords_query = self.construct_search_query()

        # Construct the URLs for both endpoints
        meta_url = f"{self.meta_url}?q={keywords_query}&api_key={self.meta_api_key}"
        openaccess_url = f"{self.openaccess_url}?q={keywords_query}&api_key={self.openaccess_api_key}"

        logging.debug(f"Constructed query for meta: {meta_url}")
        logging.debug(f"Constructed query for openaccess: {openaccess_url}")

        return [meta_url, openaccess_url]

    def collect_from_endpoints(self):
        """
        Collects data from both the meta and openaccess endpoints with pagination.

        Returns:
            list: Combined results from both endpoints.
        """
        urls = self.get_configurated_url()  # Get the list of API URLs
        combined_results = []

        for base_url in urls:  # Iterate through each base URL
            ################################# TO DO ?
            page = 1
            has_more_pages = True

            while has_more_pages:
                # PRE-CHECK: Stop if we've already collected enough articles
                max_articles = self.filter_param.get_max_articles_per_query()
                if max_articles > 0 and self.nb_art_collected >= max_articles:
                    logging.info(
                        f"Reached max_articles_per_query limit ({max_articles}). "
                        f"Already collected {self.nb_art_collected} articles. Stopping before page {page}."
                    )
                    break

                # Append pagination parameter to the base URL
                paginated_url = (
                    f"{base_url}&p={page}"  # Use 'p' for Springer API pagination
                )
                logging.debug(f"Fetching data from URL: {paginated_url}")

                # Call the API
                try:
                    response = self.api_call_decorator(paginated_url)

                    # Parse the response
                    page_data = self.parsePageResults(response, page)
                    combined_results.append(
                        page_data
                    )  # Store results from this endpoint

                    # Update article count
                    self.nb_art_collected += len(page_data["results"])

                    # Determine if more pages are available
                    if (
                        len(page_data["results"]) > 0
                        and "total" in page_data
                        and page_data["total"] > 0
                    ):
                        # Calculate expected pages based on total results
                        expected_pages = math.ceil(
                            page_data["total"] / self.max_by_page
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

                    page += 1  # Increment page number for the next request

                except Exception as e:
                    logging.error(
                        f"Error fetching or parsing data from {paginated_url}: {str(e)}"
                    )
                    has_more_pages = False  # Stop fetching on error

        return combined_results
