import asyncio
import json
import logging
import multiprocessing
import os
import time
from datetime import date
from itertools import product

import yaml

from .collectors import (
    DBLP_collector,
    Arxiv_collector,
    Elsevier_collector,
    IEEE_collector,
    Springer_collector,
    SemanticScholar_collector,
    OpenAlex_collector,
    HAL_collector,
    Istex_collector,
    GoogleScholarCollector,
)
from .async_wrapper import AsyncCollectorWrapper

# Import centralized logging utilities
try:
    from src.logging_config import ProgressTracker, log_api_start, log_api_complete
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

global lock
lock = multiprocessing.Lock()


# Global worker function for multiprocessing (must be at module level for pickling)
def _run_job_collects_worker(collect_list, api_config, output_dir, collect_name):
    """
    Worker function for multiprocessing that can be properly serialized.
    This must be at module level (not in a class) for spawn mode to work.
    """
    repo = os.path.join(output_dir, collect_name)
    
    for idx in range(len(collect_list)):
        is_last = idx == len(collect_list) - 1
        coll = collect_list[idx]
        data_query = coll["query"]
        collector_class = api_collectors[coll["api"]]
        api_key = None
        inst_token = None
        
        if coll["api"] in api_config:
            api_key = api_config[coll["api"]].get("api_key")
            if coll["api"] == "Elsevier" and "inst_token" in api_config[coll["api"]]:
                inst_token = api_config[coll["api"]]["inst_token"]
                logging.debug(f"Using institutional token for Elsevier API")
        
        try:
            # Initialize collector
            if coll["api"] == "Elsevier" and inst_token:
                current_coll = collector_class(data_query, repo, api_key, inst_token)
            else:
                current_coll = collector_class(data_query, repo, api_key)
            
            # Run collection
            res = current_coll.runCollect()
            
            # Update state
            _update_state_worker(repo, current_coll.api_name, str(current_coll.collectId), res)

            logging.debug(f"Completed collection for {coll['api']} query {data_query.get('id_collect', 'unknown')}")
            
        except Exception as e:
            logging.error(f"Error during collection for {coll['api']}: {str(e)}")
            # Mark as failed in state
            error_state = {"state": -1, "error": str(e), "last_page": 0}
            try:
                _update_state_worker(repo, coll["api"], str(data_query.get("id_collect", 0)), error_state)
            except Exception as state_error:
                logging.error(f"Failed to update state after error: {str(state_error)}")

        # Note: Removed fixed 2-second delay - rate limiting is now handled per-API
        # by individual collectors using configured rate limits from api.config.yml


def _update_state_worker(repo, api, idx, state_data):
    """Helper function to update state file in a thread-safe way"""
    state_path = os.path.join(repo, "state_details.json")
    
    with lock:
        if os.path.isfile(state_path):
            with open(state_path, encoding="utf-8") as read_file:
                state_orig = json.load(read_file)
            
            # Update query state
            for k in state_data:
                state_orig["details"][api]["by_query"][str(idx)][k] = state_data[k]
            
            # Check if API is finished
            finished_local = True
            for k in state_orig["details"][api]["by_query"]:
                q = state_orig["details"][api]["by_query"][k]
                if q["state"] != 1:
                    finished_local = False
            
            if finished_local:
                state_orig["details"][api]["state"] = 1
            else:
                state_orig["details"][api]["state"] = 0
            
            # Check if all APIs are finished
            finished_global = True
            for api_ in state_orig["details"]:
                if state_orig["details"][api_]["state"] != 1:
                    finished_global = False
            
            if finished_global:
                state_orig["global"] = 1
            else:
                state_orig["global"] = 0
            
            # Save state
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state_orig, f, ensure_ascii=False, indent=4)


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
        logging.info("Initializing collection")
        self.main_config = main_config
        self.api_config = api_config
        self.state_details = {}
        self.state_details = {"global": -1, "details": {}}
        self.init_collection_collect()
        
        # Initialize StateManager for SQLite-based state persistence (Phase 1B)
        # This reduces lock contention from JSON file I/O by batching updates
        self.state_manager = None
        self.use_state_db = os.environ.get('USE_STATE_DB', '').lower() == 'true'
        if self.use_state_db:
            logging.info("StateManager enabled (USE_STATE_DB=true)")
            try:
                from src.gui.backend.services.state_manager import StateManager
                repo = self.get_current_repo()
                db_path = os.path.join(repo, 'state.db')
                self.state_manager = StateManager(db_path)
            except ImportError:
                logging.warning("StateManager not available - GUI removed. USE_STATE_DB=true ignored.")

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
            logger.warning(f"Missing API keys: {', '.join(missing_keys)} - these collections will likely fail")
            return False

        logger.debug("API key validation passed")
        return True

    def init_progress_tracking(self, total_jobs):
        """Initialize progress tracking"""
        self.total_jobs = total_jobs
        self.completed_jobs = 0
        self.progress_lock = multiprocessing.Lock()
    
    def update_progress(self):
        """Update progress counter (thread-safe)"""
        with self.progress_lock:
            self.completed_jobs += 1
            progress_pct = (self.completed_jobs / self.total_jobs) * 100
            logging.info(f"Progress: {self.completed_jobs}/{self.total_jobs} ({progress_pct:.1f}%) collections completed")

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
                "last_page": 0
            }
            try:
                self.update_state_details(collector.api_name, str(collector.collectId), error_state)
            except Exception as state_error:
                logging.error(f"Failed to update state after error: {str(state_error)}")
            self.update_progress()

    def run_job_collects(self, collect_list):
        for idx in range(len(collect_list)):
            is_last = idx == len(collect_list) - 1
            coll = collect_list[idx]
            data_query = coll["query"]
            collector = api_collectors[coll["api"]]
            api_key = None
            inst_token = None  # For Elsevier institutional token
            
            if coll["api"] in self.api_config:
                api_key = self.api_config[coll["api"]]["api_key"]
                # Check for institutional token (Elsevier only)
                if coll["api"] == "Elsevier" and "inst_token" in self.api_config[coll["api"]]:
                    inst_token = self.api_config[coll["api"]]["inst_token"]
                    logging.info(f"Using institutional token for Elsevier API")

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

        if two_list_k:
            queries = []
            for keyword_group, year, api in combinations:
                query = {"keyword": keyword_group, "year": year, "api": api}
                # Add semantic_scholar_mode for SemanticScholar API
                if api == "SemanticScholar":
                    query["semantic_scholar_mode"] = semantic_scholar_mode
                queries.append(query)
        else:
            queries = []
            for keyword_group, year, api in combinations:
                query = {"keyword": [keyword_group], "year": year, "api": api}
                # Add semantic_scholar_mode for SemanticScholar API
                if api == "SemanticScholar":
                    query["semantic_scholar_mode"] = semantic_scholar_mode
                queries.append(query)
        logger.debug(f"Generated {len(queries)} total queries across {len(self.main_config['apis'])} APIs")
        queries_by_api = {}
        for query in queries:
            if query["api"] not in queries_by_api:
                queries_by_api[query["api"]] = []
            queries_by_api[query["api"]].append(
                {"keyword": query["keyword"], "year": query["year"]}
            )

        return queries_by_api

    def load_state_details(self):
        repo = self.get_current_repo()
        state_path = os.path.join(repo, "state_details.json")
        if os.path.isfile(state_path):
            with open(state_path, encoding="utf-8") as read_file:
                self.state_details = json.load(read_file)
        else:
            logging.warning("Missing state details file")

    def update_state_details(self, api, idx, state_data):
        repo = self.get_current_repo()
        state_path = os.path.join(repo, "state_details.json")
        
        # Use lock for entire read-modify-write operation to prevent race conditions
        with lock:
            if os.path.isfile(state_path):
                with open(state_path, encoding="utf-8") as read_file:
                    state_orig = json.load(read_file)

                for k in state_data:
                    state_orig["details"][api]["by_query"][str(idx)][k] = state_data[k]

                finished_local = True
                for k in state_orig["details"][api]["by_query"]:
                    q = state_orig["details"][api]["by_query"][k]
                    if q["state"] != 1:
                        finished_local = False

                if finished_local:
                    state_orig["details"][api]["state"] = 1
                else:
                    state_orig["details"][api]["state"] = 0

                finished_global = True
                for api_ in state_orig["details"]:
                    if state_orig["details"][api_]["state"] != 1:
                        finished_global = False

                if finished_global:
                    state_orig["global"] = 1
                else:
                    state_orig["global"] = 0

                self.state_details = state_orig
                self.save_state_details()
            else:
                logging.warning("Missing state details file")

    def init_state_details(self, queries_by_api):
        """
        Init. state details files used to follow the collect history
        """
        self.state_details["global"] = 0
        self.state_details["details"] = {}
        for api in queries_by_api:
            if api not in self.state_details["details"]:
                self.state_details["details"][api] = {}
                self.state_details["details"][api]["state"] = -1
                self.state_details["details"][api]["by_query"] = {}
                queries = queries_by_api[api]
                for idx in range(len(queries)):
                    self.state_details["details"][api]["by_query"][idx] = {}
                    self.state_details["details"][api]["by_query"][idx]["state"] = -1
                    self.state_details["details"][api]["by_query"][idx][
                        "id_collect"
                    ] = idx
                    self.state_details["details"][api]["by_query"][idx]["last_page"] = 0
                    self.state_details["details"][api]["by_query"][idx]["total_art"] = 0
                    self.state_details["details"][api]["by_query"][idx]["coll_art"] = 0
                    self.state_details["details"][api]["by_query"][idx][
                        "update_date"
                    ] = str(date.today())
                    for k in queries[idx]:
                        if k not in self.state_details["details"][api]["by_query"][idx]:
                            self.state_details["details"][api]["by_query"][idx][k] = (
                                queries[idx][k]
                            )

    def save_state_details(self):
        repo = self.get_current_repo()
        state_path = os.path.join(repo, "state_details.json")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(self.state_details, f, ensure_ascii=False, indent=4)

    def init_collection_collect(self):
        repo = self.get_current_repo()
        state_file = os.path.join(repo, "state_details.json")
        
        # Reinitialize if:
        # 1. Directory doesn't exist (first run), OR
        # 2. State file doesn't exist (partial collection), OR
        # 3. State is marked complete but force_restart is needed (handled by caller)
        if not os.path.isdir(repo) or not os.path.isfile(state_file):
            if not os.path.isdir(repo):
                os.makedirs(repo)
            with open(os.path.join(repo, "config_used.yml"), "w") as f:
                yaml.dump(self.main_config, f)
            logging.info("Building query composition")
            queries_by_api = self.queryCompositor()

            self.init_state_details(queries_by_api)

            self.save_state_details()

        self.load_state_details()

    def create_collects_jobs(self):
        """Validate API keys and create collection jobs"""
        logger = logging.getLogger(__name__)

        # Validate API keys before starting
        self.validate_api_keys()

        # Create the collection of jobs depending of the history and run it in parallel
        jobs_list = []
        n_coll = 0
        if self.state_details["global"] == 0 or self.state_details["global"] == -1:
            for api in self.state_details["details"]:
                current_api_job = []
                if (
                    self.state_details["details"][api]["state"] == -1
                    or self.state_details["details"][api]["state"] == 0
                ):
                    for k in self.state_details["details"][api]["by_query"]:
                        query = self.state_details["details"][api]["by_query"][k]
                        if query["state"] != 1:
                            current_api_job.append({"query": query, "api": api})
                            n_coll += 1
                    if len(current_api_job) > 0:
                        jobs_list.append(current_api_job)

        # Check if there are any jobs to process
        if len(jobs_list) == 0:
            logger.warning("No collections to conduct. Collection may already be complete.")
            logger.warning("To restart collection, delete the output directory or reset state.")
            return

        # Calculate number of processes - simplified logic
        num_cores = min(len(jobs_list), multiprocessing.cpu_count())
        if num_cores < 1:
            num_cores = 1

        logger.info(f"Starting sync collection: {n_coll} queries using {num_cores} parallel processes")

        # Initialize progress tracking
        self.init_progress_tracking(len(jobs_list))

        # Prepare data for worker functions (must be serializable)
        worker_args = [
            (job_list, self.api_config, self.main_config["output_dir"], self.main_config["collect_name"])
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

    async def create_collects_jobs_async(self):
        """
        Async version of create_collects_jobs using AsyncCollectorWrapper.

        This enables parallel collection of multiple APIs using asyncio
        with per-API rate limiting and concurrency control.

        Optionally uses StateManager for SQLite-based state persistence (Phase 1B).
        Expected speedup: 2.5-3x (async) to 3-4x (async + StateManager).
        """
        logger = logging.getLogger(__name__)

        # Validate API keys before starting
        self.validate_api_keys()

        # Build list of collections to run
        collections = []
        n_coll = 0

        if self.state_details["global"] == 0 or self.state_details["global"] == -1:
            for api in self.state_details["details"]:
                if (
                    self.state_details["details"][api]["state"] == -1
                    or self.state_details["details"][api]["state"] == 0
                ):
                    for k in self.state_details["details"][api]["by_query"]:
                        query = self.state_details["details"][api]["by_query"][k]
                        if query["state"] != 1:
                            collections.append({
                                'api': api,
                                'query': query,
                                'path': self.get_current_repo(),
                                'key': self.api_config.get(api, {}).get('api_key')
                            })
                            n_coll += 1

        num_apis = len(set(c['api'] for c in collections))
        logger.info(f"Starting async collection: {n_coll} queries across {num_apis} APIs")

        # Initialize progress tracking
        self.init_progress_tracking(n_coll)

        # Create async wrapper and run collections in parallel
        wrapper = AsyncCollectorWrapper()

        try:
            # Run collections sequentially per API, parallel across APIs
            # This naturally respects rate limits without global coordination
            start_time = time.time()

            results = await wrapper.run_collections_sequential_per_api(collections)

            elapsed_time = time.time() - start_time
            logger.info(f"Async collection completed in {elapsed_time:.1f}s")

            # Update state with results
            # Use StateManager batch updates if enabled (Phase 1B optimization)
            if self.state_manager:
                logger.debug("Using StateManager for batch state updates...")

                # Group updates by API for batch processing
                updates_by_api = {}
                for i, result in enumerate(results):
                    if i < len(collections):
                        api = collections[i]['api']
                        query_id = str(collections[i]['query'].get('id_collect', i))

                        if api not in updates_by_api:
                            updates_by_api[api] = {}

                        updates_by_api[api][query_id] = result

                # Batch update queries in StateManager (10 per write vs 1 per write)
                for api, updates in updates_by_api.items():
                    try:
                        await self.state_manager.batch_update_queries(api, updates)
                        logger.debug(f"StateManager: Batched {len(updates)} updates for {api}")
                    except Exception as e:
                        logger.warning(f"StateManager batch update failed for {api}: {str(e)}")
                        # Fall back to JSON updates
                        for query_id, result in updates.items():
                            self.update_state_details(api, query_id, result)
            else:
                # Fall back to JSON-based state updates (default behavior)
                for i, result in enumerate(results):
                    if i < len(collections):
                        api = collections[i]['api']
                        query_id = collections[i]['query'].get('id_collect', i)

                        try:
                            self.update_state_details(api, str(query_id), result)
                        except Exception as e:
                            logging.error(f"Error updating state for {api} query {query_id}: {str(e)}")

        except Exception as e:
            logging.error(f"Error during async collection: {str(e)}")
            raise

    async def run_async_collection(self):
        """
        High-level async collection runner.

        This is the main entry point for running collections asynchronously.
        Optionally initializes StateManager for SQLite-based state persistence.
        """
        logger = logging.getLogger(__name__)

        try:
            # Initialize StateManager if enabled (Phase 1B optimization)
            if self.state_manager:
                logger.debug("Initializing StateManager for SQLite persistence...")
                await self.state_manager.initialize()
                logger.debug("StateManager initialized - using SQLite for state persistence")

            await self.create_collects_jobs_async()

            logger.info("All collections completed successfully")

        except Exception as e:
            logging.error(f"Async collection failed: {str(e)}")
            raise
