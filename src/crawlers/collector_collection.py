import logging
import multiprocessing
import os
from itertools import product

import yaml

from .collectors import (
    Arxiv_collector,
    DBLP_collector,
    Elsevier_collector,
    GoogleScholarCollector,
    HAL_collector,
    IEEE_collector,
    Istex_collector,
    OpenAlex_collector,
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
    "DBLP": DBLP_collector,
    "Arxiv": Arxiv_collector,
    "Elsevier": Elsevier_collector,
    "IEEE": IEEE_collector,
    "Springer": Springer_collector,
    "SemanticScholar": SemanticScholar_collector,
    "OpenAlex": OpenAlex_collector,
    "HAL": HAL_collector,
    "ISTEX": Istex_collector,
    "GoogleScholar": GoogleScholarCollector,
}


# Global worker function for multiprocessing (must be at module level for pickling)
def _run_job_collects_worker(collect_list, api_config, output_dir, collect_name):
    """
    Worker function for multiprocessing that can be properly serialized.
    This must be at module level (not in a class) for spawn mode to work.
    """
    # Use absolute path to avoid issues with different working directories in spawn mode
    repo = os.path.abspath(os.path.join(output_dir, collect_name))

    for idx in range(len(collect_list)):
        coll = collect_list[idx]
        data_query = coll["query"]
        collector_class = api_collectors[coll["api"]]
        api_key = None
        inst_token = None

        if coll["api"] in api_config:
            api_key = api_config[coll["api"]].get("api_key")
            if coll["api"] == "Elsevier" and "inst_token" in api_config[coll["api"]]:
                inst_token = api_config[coll["api"]]["inst_token"]
                logging.debug("Using institutional token for Elsevier API")

        try:
            # Initialize collector
            if coll["api"] == "Elsevier" and inst_token:
                current_coll = collector_class(data_query, repo, api_key, inst_token)
            else:
                current_coll = collector_class(data_query, repo, api_key)

            # Run collection
            res = current_coll.runCollect()

            logging.debug(
                f"Completed collection for {coll['api']} query {data_query.get('id_collect', 'unknown')}: {res.get('coll_art', 0)} articles"
            )

        except Exception as e:
            logging.error(f"Error during collection for {coll['api']}: {str(e)}")

        # Note: Removed fixed 2-second delay - rate limiting is now handled per-API
        # by individual collectors using configured rate limits from api.config.yml


class Filter_param:
    def __init__(self, year, keywords, focus):
        # Initialize the parameters
        self.year = year
        # Keywords is now a list of lists to support multiple sets
        self.keywords = keywords
        self.focus = focus

    def get_dict_param(self):
        # Return the instance's dictionary representation
        return self.__dict__

    def get_year(self):
        return self.year

    def get_keywords(self):
        return self.keywords

    def get_focus(self):
        return self.focus


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

    def init_progress_tracking(self, total_jobs):
        """Initialize progress tracking"""
        self.total_jobs = total_jobs
        self.completed_jobs = 0
        self.progress_lock = multiprocessing.Lock()

    def update_progress(self):
        """Update progress counter (thread-safe) - uses print() to bypass log level filtering"""
        with self.progress_lock:
            self.completed_jobs += 1
            progress_pct = (self.completed_jobs / self.total_jobs) * 100
            # Use print() instead of logging to ensure visibility regardless of log level
            print(
                f"Progress: {self.completed_jobs}/{self.total_jobs} ({progress_pct:.1f}%) collections completed"
            )

    def job_collect(self, collector):
        try:
            res = collector.runCollect()
            self.update_state_details(collector.api_name, str(collector.collectId), res)
            self.update_progress()
        except Exception as e:
            logging.error(f"Error during collection for {collector.api_name}: {str(e)}")
            # Mark as failed in state
            error_state = {
                "state": -1,  # -1 indicates error
                "error": str(e),
                "last_page": 0,
            }
            try:
                self.update_state_details(
                    collector.api_name, str(collector.collectId), error_state
                )
            except Exception as state_error:
                logging.error(f"Failed to update state after error: {str(state_error)}")
            self.update_progress()

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
            res = current_coll.runCollect()
            self.update_state_details(
                current_coll.api_name, str(current_coll.collectId), res
            )

            # Note: Removed fixed 2-second delay - rate limiting is now handled per-API
            # by individual collectors using configured rate limits from api.config.yml

    def get_current_repo(self):
        return os.path.join(
            self.main_config["output_dir"], self.main_config["collect_name"]
        )

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

        # Create jobs list, skipping already-completed queries
        repo = self.get_current_repo()
        jobs_list = []
        n_coll = 0
        n_skipped = 0

        for api in queries_by_api:
            current_api_job = []
            queries = queries_by_api[api]

            for idx, query in enumerate(queries):
                # Check if this query is already complete (has result files)
                if self._query_is_complete(repo, api, idx):
                    n_skipped += 1
                    logger.debug(f"Skipping {api} query {idx} (already has results)")
                    continue

                # Add query to job list
                query["id_collect"] = idx
                query["total_art"] = 0  # Unknown until first API response
                query["last_page"] = 0  # Start from page 0
                query["coll_art"] = 0  # No articles collected yet
                query["state"] = 0  # Incomplete (0=incomplete, 1=complete, -1=error)
                current_api_job.append({"query": query, "api": api})
                n_coll += 1

            if len(current_api_job) > 0:
                jobs_list.append(current_api_job)

        # Log summary
        if n_skipped > 0:
            logger.info(
                f"Skipped {n_skipped} already-completed queries (idempotent re-run)"
            )

        # Check if there are any jobs to process
        if len(jobs_list) == 0:
            logger.warning(
                "No collections to conduct. All queries already have results."
            )
            logger.warning(
                "To restart collection, delete the API directories in the output folder."
            )
            return

        # Calculate number of processes - simplified logic
        num_cores = min(len(jobs_list), multiprocessing.cpu_count())
        if num_cores < 1:
            num_cores = 1

        print(
            f"Starting sync collection: {n_coll} queries using {num_cores} parallel processes"
        )

        # Initialize progress tracking
        self.init_progress_tracking(len(jobs_list))

        # Prepare data for worker functions (must be serializable)
        worker_args = [
            (
                job_list,
                self.api_config,
                self.main_config["output_dir"],
                self.main_config["collect_name"],
            )
            for job_list in jobs_list
        ]

        pool = multiprocessing.Pool(processes=num_cores)
        try:
            # Use starmap to pass multiple arguments to worker function
            result = pool.starmap_async(_run_job_collects_worker, worker_args)
            result.wait()
        finally:
            pool.close()
            pool.join()

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
