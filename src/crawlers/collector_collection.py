import logging
import os
import threading
from collections import defaultdict
from itertools import product
from queue import Queue

import yaml
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from src.config_defaults import DEFAULT_OUTPUT_DIR

from .collectors import (
    Arxiv_collector,
    BioRxiv_collector,
    DBLP_collector,
    Elsevier_collector,
    GoogleScholarCollector,
    HAL_collector,
    IEEE_collector,
    Istex_collector,
    OpenAlex_collector,
    PubMed_collector,
    PubMedCentral_collector,
    SemanticScholar_collector,
    Springer_collector,
)

# Import centralized logging utilities
try:
    from src.logging_config import ProgressTracker, log_api_complete, log_api_start
except ImportError:
    # Fallback if logging_config not available
    ProgressTracker = None
    log_api_start = None
    log_api_complete = None

api_collectors = {
    "BioRxiv": BioRxiv_collector,
    "DBLP": DBLP_collector,
    "Arxiv": Arxiv_collector,
    "Elsevier": Elsevier_collector,
    "IEEE": IEEE_collector,
    "Springer": Springer_collector,
    "SemanticScholar": SemanticScholar_collector,
    "OpenAlex": OpenAlex_collector,
    "HAL": HAL_collector,
    "Istex": Istex_collector,
    "GoogleScholar": GoogleScholarCollector,
    "PubMed": PubMed_collector,
    "PubMedCentral": PubMedCentral_collector,
}


# Thread worker function (processes all queries for one API)


def _sanitize_error_message(error_msg):
    """
    Remove sensitive information (API keys, tokens) from error messages.

    Args:
        error_msg: Error message string that may contain sensitive parameters

    Returns:
        str: Sanitized error message with sensitive parameters masked
    """
    import re

    # Replace API keys in URLs within error messages
    error_msg = re.sub(r"([?&]api[Kk]ey=)[^&\s]+", r"\1***REDACTED***", error_msg)
    error_msg = re.sub(r"([?&]apikey=)[^&\s]+", r"\1***REDACTED***", error_msg)
    error_msg = re.sub(r"([?&]key=)[^&\s]+", r"\1***REDACTED***", error_msg)
    error_msg = re.sub(r"([?&]token=)[^&\s]+", r"\1***REDACTED***", error_msg)
    return error_msg


def _run_job_collects_worker(
    api_name, collect_list, api_config, output_dir, collect_name, progress_queue
):
    """
    Thread worker function for one API.
    Processes all queries for the assigned API and sends progress updates via queue.

    Args:
        api_name: Name of the API (e.g., "SemanticScholar")
        collect_list: List of query dicts for this API
        api_config: API configuration dict
        output_dir: Output directory path
        collect_name: Collection name
        progress_queue: Queue for sending progress updates to main thread
    """
    # Use absolute path
    repo = os.path.abspath(os.path.join(output_dir, collect_name))

    # Process each query for this API
    for coll_dict in collect_list:
        data_query = coll_dict["query"]
        query_id = data_query.get("id_collect", 0)
        collector_class = api_collectors[api_name]
        api_key = None
        inst_token = None

        if api_name in api_config:
            api_key = api_config[api_name].get("api_key")
            if api_name == "Elsevier" and "inst_token" in api_config[api_name]:
                token_value = api_config[api_name]["inst_token"]
                # Reject placeholder/invalid tokens
                INVALID_TOKENS = {"YOUR_INSTITUTIONAL_TOKEN", "NA", "TODO", "", None}
                if token_value not in INVALID_TOKENS and not (
                    isinstance(token_value, str) and token_value.startswith("YOUR_")
                ):
                    inst_token = token_value
                    logging.debug("Using institutional token for Elsevier API")

        try:
            # Initialize collector
            if api_name == "Elsevier" and inst_token:
                current_coll = collector_class(data_query, repo, api_key, inst_token)
            else:
                current_coll = collector_class(data_query, repo, api_key)

            # Run collection
            res = current_coll.runCollect()
            articles_collected = res.get("coll_art", 0)

            logging.debug(
                f"Completed collection for {api_name} query {query_id}: {articles_collected} articles"
            )

            # Send progress update to main thread via queue
            progress_queue.put(
                {
                    "api": api_name,
                    "query_id": query_id,
                    "articles_collected": articles_collected,
                    "success": True,
                }
            )

        except Exception as e:
            # Sanitize error message to remove API keys
            sanitized_error = _sanitize_error_message(str(e))
            logging.error(
                f"Error during collection for {api_name} query {query_id}: {sanitized_error}"
            )
            # Send error progress update
            progress_queue.put(
                {
                    "api": api_name,
                    "query_id": query_id,
                    "articles_collected": 0,
                    "success": False,
                    "error": sanitized_error,
                }
            )

    # Note: Rate limiting is handled per-API by individual collectors
    # using configured rate limits from api.config.yml


class CollectCollection:
    def __init__(self, main_config, api_config):
        print("Initializing collection")
        self.main_config = main_config
        self.api_config = api_config
        self.init_collection_collect()

    def validate_api_keys(self):
        """Validate that required API keys are present before starting collection"""
        logger = logging.getLogger(__name__)
        apis_requiring_keys = {
            "IEEE": "api_key",
            "Springer": "api_key",
            "Elsevier": ["api_key", "inst_token"],
        }

        missing_keys = []
        apis_to_use = self.main_config.get("apis", [])

        for api in apis_to_use:
            if api in apis_requiring_keys:
                required_keys = apis_requiring_keys[api]
                if not isinstance(required_keys, list):
                    required_keys = [required_keys]

                api_config = self.api_config.get(api, {})
                for key in required_keys:
                    if not api_config.get(key):
                        missing_keys.append(f"{api}.{key}")

        if missing_keys:
            logger.warning(
                f"Missing API keys: {', '.join(missing_keys)} - these collections will likely fail"
            )
            return False

        logger.debug("API key validation passed")
        return True

    def run_job_collects(self, collect_list):
        for idx in range(len(collect_list)):
            coll = collect_list[idx]
            data_query = coll["query"]
            collector = api_collectors[coll["api"]]
            api_key = None
            inst_token = None  # For Elsevier institutional token

            if coll["api"] in self.api_config:
                api_key = self.api_config[coll["api"]]["api_key"]
                # Check for institutional token (Elsevier only)
                if (
                    coll["api"] == "Elsevier"
                    and "inst_token" in self.api_config[coll["api"]]
                ):
                    inst_token = self.api_config[coll["api"]]["inst_token"]
                    logging.info("Using institutional token for Elsevier API")

            repo = self.get_current_repo()

            # Initialize collector with institutional token if applicable
            if coll["api"] == "Elsevier" and inst_token:
                current_coll = collector(data_query, repo, api_key, inst_token)
            else:
                current_coll = collector(data_query, repo, api_key)
            current_coll.runCollect()

            # Note: Removed fixed 2-second delay - rate limiting is now handled per-API
            # by individual collectors using configured rate limits from api.config.yml

    def get_current_repo(self):
        output_dir = self.main_config.get("output_dir", DEFAULT_OUTPUT_DIR)
        return os.path.join(output_dir, self.main_config["collect_name"])

    def queryCompositor(self):
        """
        Generates all potential combinations of keyword groups, years, APIs, and fields.
            list: A list of dictionaries, each representing a unique combination.
        """

        # Generate all combinations of keywords from two different groups
        keyword_combinations = []
        two_list_k = False
        #### CASE EVERYTHING OK
        if (
            len(self.main_config["keywords"]) == 2
            and len(self.main_config["keywords"][0]) != 0
            and len(self.main_config["keywords"][1]) != 0
        ):
            two_list_k = True
            keyword_combinations = [
                list(pair)
                for pair in product(
                    self.main_config["keywords"][0], self.main_config["keywords"][1]
                )
            ]
        #### CASE ONLY ONE LIST
        elif (
            len(self.main_config["keywords"]) == 2
            and len(self.main_config["keywords"][0]) != 0
            and len(self.main_config["keywords"][1]) == 0
        ) or (
            len(self.main_config["keywords"]) == 1
            and len(self.main_config["keywords"][0]) != 0
        ):
            keyword_combinations = self.main_config["keywords"][0]

        logger = logging.getLogger(__name__)
        logger.debug(f"Generated {len(keyword_combinations)} keyword combinations")

        # Generate all combinations using Cartesian product
        ### ADD LETTER FIELDS
        # combinations = product(keyword_combinations, self.years, self.apis, self.fields)
        combinations = product(
            keyword_combinations, self.main_config["years"], self.main_config["apis"]
        )

        # Create a list of dictionaries with the combinations
        # Include semantic_scholar_mode for SemanticScholar API
        semantic_scholar_mode = self.main_config.get("semantic_scholar_mode", "regular")
        # Get max_articles_per_query from config (default to -1 = unlimited)
        max_articles_per_query = self.main_config.get("max_articles_per_query", -1)

        if two_list_k:
            queries = []
            for keyword_group, year, api in combinations:
                query = {
                    "keyword": keyword_group,
                    "year": year,
                    "api": api,
                    "max_articles_per_query": max_articles_per_query,
                }
                # Add semantic_scholar_mode for SemanticScholar API
                if api == "SemanticScholar":
                    query["semantic_scholar_mode"] = semantic_scholar_mode
                queries.append(query)
        else:
            queries = []
            for keyword_group, year, api in combinations:
                query = {
                    "keyword": [keyword_group],
                    "year": year,
                    "api": api,
                    "max_articles_per_query": max_articles_per_query,
                }
                # Add semantic_scholar_mode for SemanticScholar API
                if api == "SemanticScholar":
                    query["semantic_scholar_mode"] = semantic_scholar_mode
                queries.append(query)
        logger.debug(
            f"Generated {len(queries)} total queries across {len(self.main_config['apis'])} APIs"
        )
        queries_by_api = {}
        for query in queries:
            if query["api"] not in queries_by_api:
                queries_by_api[query["api"]] = []
            # Preserve all query fields (max_articles_per_query, semantic_scholar_mode, etc.)
            query_dict = {
                "keyword": query["keyword"],
                "year": query["year"],
                "max_articles_per_query": query["max_articles_per_query"],
            }
            # Add optional semantic_scholar_mode if present
            if "semantic_scholar_mode" in query:
                query_dict["semantic_scholar_mode"] = query["semantic_scholar_mode"]
            queries_by_api[query["api"]].append(query_dict)

        return queries_by_api

    def init_collection_collect(self):
        """
        Initialize collection directory and save config snapshot.

        Creates output directory if needed and saves a snapshot of the config
        for use by aggregation later.
        """
        repo = self.get_current_repo()

        # Create directory and save config snapshot on first run
        if not os.path.isdir(repo):
            os.makedirs(repo)
            logging.info(f"Created collection directory: {repo}")

        # Always save/update config snapshot to ensure it's current
        config_path = os.path.join(repo, "config_used.yml")
        with open(config_path, "w") as f:
            yaml.dump(self.main_config, f)
        logging.debug(f"Saved config snapshot to: {config_path}")

    def _query_is_complete(self, repo, api, query_idx):
        """
        Check if a query is complete by checking for result files.

        Args:
            repo: Collection directory path
            api: API name (e.g., 'SemanticScholar')
            query_idx: Query index (e.g., 0, 1, 2)

        Returns:
            bool: True if query has result files, False otherwise
        """
        query_dir = os.path.join(repo, api, str(query_idx))

        # Query is complete if directory exists and has page files
        if not os.path.isdir(query_dir):
            return False

        # Check for page files (e.g., page_1, page_2, etc.)
        try:
            files = os.listdir(query_dir)
            # Consider complete if it has any files (page_* or other result files)
            has_results = len(files) > 0
            return has_results
        except (PermissionError, OSError):
            # If we can't read the directory, assume it's not complete
            return False

    def create_collects_jobs(self):
        """
        Create collection jobs and run them in parallel.

        Uses file existence checks for idempotent collections:
        - Skips queries that already have result files
        - Allows safe re-runs without duplicating API calls
        """
        logger = logging.getLogger(__name__)

        # Validate API keys before starting
        self.validate_api_keys()

        # Generate all queries from config
        print("Building query composition")
        queries_by_api = self.queryCompositor()

        # Create grouped jobs dict (one list per API), skipping already-completed queries
        repo = self.get_current_repo()
        jobs_by_api = {}  # Grouped: {"API_name": [query1, query2, ...]}
        n_coll = 0
        n_skipped = 0

        for api in queries_by_api:
            queries = queries_by_api[api]
            api_jobs = []

            for idx, query in enumerate(queries):
                # Check if this query is already complete (has result files)
                if self._query_is_complete(repo, api, idx):
                    n_skipped += 1
                    logger.debug(f"Skipping {api} query {idx} (already has results)")
                    continue

                # Add query to API's job list
                query["id_collect"] = idx
                query["total_art"] = 0  # Unknown until first API response
                query["last_page"] = 0  # Start from page 0
                query["coll_art"] = 0  # No articles collected yet
                query["state"] = 0  # Incomplete (0=incomplete, 1=complete, -1=error)
                api_jobs.append({"query": query, "api": api})
                n_coll += 1

            # Only add API if it has queries to process
            if api_jobs:
                jobs_by_api[api] = api_jobs

        # Log summary
        if n_skipped > 0:
            logger.info(
                f"Skipped {n_skipped} already-completed queries (idempotent re-run)"
            )

        # Check if there are any jobs to process
        if len(jobs_by_api) == 0:
            logger.warning(
                "No collections to conduct. All queries already have results."
            )
            logger.warning(
                "To restart collection, delete the API directories in the output folder."
            )
            return

        # One thread per API
        num_threads = len(jobs_by_api)
        num_apis = len(jobs_by_api)
        print(
            f"Starting collection: {n_coll} queries across {num_apis} API(s) using {num_threads} threads (1 per API)\n"
        )

        # Create per-API progress tracking
        api_progress_bars = {}
        api_stats = defaultdict(lambda: {"completed": 0, "total": 0, "articles": 0})

        # Initialize progress bars for each API
        for api_name, api_jobs in sorted(jobs_by_api.items()):
            query_count = len(api_jobs)
            api_stats[api_name]["total"] = query_count
            api_progress_bars[api_name] = tqdm(
                total=query_count,
                desc=f"{api_name:20s}",
                unit="query",
                position=len(api_progress_bars),
                leave=True,
            )

        # Create shared progress queue
        progress_queue = Queue()

        # Extract output_dir with default
        output_dir = self.main_config.get("output_dir", DEFAULT_OUTPUT_DIR)

        # Create one thread per API
        threads = []
        for api_name, api_jobs in jobs_by_api.items():
            thread = threading.Thread(
                target=_run_job_collects_worker,
                args=(
                    api_name,
                    api_jobs,
                    self.api_config,
                    output_dir,
                    self.main_config["collect_name"],
                    progress_queue,
                ),
                name=f"Worker-{api_name}",
            )
            thread.start()
            threads.append(thread)

        # Monitor progress queue in main thread
        completed_count = 0
        total_queries = sum(len(api_jobs) for api_jobs in jobs_by_api.values())

        try:
            # Redirect logging output to work with tqdm progress bars
            with logging_redirect_tqdm(loggers=[logging.root]):
                while completed_count < total_queries:
                    try:
                        # Get result from queue with timeout
                        result = progress_queue.get(timeout=0.1)

                        # Update stats
                        api_name = result["api"]
                        articles = result["articles_collected"]
                        api_stats[api_name]["completed"] += 1
                        api_stats[api_name]["articles"] += articles

                        # Update progress bar
                        if api_name in api_progress_bars:
                            pbar = api_progress_bars[api_name]
                            pbar.update(1)
                            pbar.set_postfix(
                                {"papers": api_stats[api_name]["articles"]}
                            )

                            # Log milestone when query completes
                            completed = api_stats[api_name]["completed"]
                            total = api_stats[api_name]["total"]
                            total_articles = api_stats[api_name]["articles"]

                            # Log at 25%, 50%, 75%, and 100% completion
                            if (
                                completed % max(1, total // 4) == 0
                                or completed == total
                            ):
                                logging.debug(
                                    f"[{api_name}] Progress: {completed}/{total} queries | {total_articles} papers collected"
                                )

                        completed_count += 1

                    except Exception:
                        # Check if all threads are done
                        if not any(t.is_alive() for t in threads):
                            break
                        continue

        finally:
            # Wait for all threads to complete
            for thread in threads:
                thread.join()

            # Close all progress bars
            for pbar in api_progress_bars.values():
                pbar.close()

            # Print final summary
            print("\n" + "=" * 60)
            print("Collection Complete - Summary:")
            print("=" * 60)
            for api_name in sorted(api_stats.keys()):
                stats = api_stats[api_name]
                print(
                    f"{api_name:20s}: {stats['completed']:3d} queries | {stats['articles']:,} papers"
                )
                logging.info(
                    f"[{api_name}] Complete: {stats['articles']} papers from {stats['completed']} queries"
                )
            print("=" * 60 + "\n")

        # FIRST ATTEMPT > not ordered by api > could lead to ratelimit overload
        # random.shuffle(jobs_list)
        # coll_coll=[]
        # for job in jobs_list:
        #    data_query=job["query"]
        #    collector=api_collectors[job["api"]]
        #    api_key=None
        #    if(job["api"] in self.api_config.keys()):
        #        api_key = self.api_config[job["api"]]["api_key"]
        #    repo=self.get_current_repo()
        #    coll_coll.append(collector(data_query, repo,api_key))

        # result=pool.map_async(self.job_collect, coll_coll)
