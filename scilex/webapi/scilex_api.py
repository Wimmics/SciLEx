"""FastAPI backend for SciLEx web interface.

Provides REST endpoints for paper collection, aggregation, filtering, and configuration management.
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from scilex.config_defaults import DEFAULT_OUTPUT_DIR
from scilex.crawlers.collector_collection import CollectCollection

# Project root for config file paths
PROJECT_ROOT = Path(__file__).parent.parent.parent

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class JobLogHandler(logging.Handler):
    """Captures log lines into a pipeline job's log list."""

    def __init__(self, job_dict: dict[str, Any], max_lines: int = 500):
        super().__init__()
        self._job = job_dict
        self._max_lines = max_lines
        self._job.setdefault("logs", [])

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            logs = self._job["logs"]
            logs.append(msg)
            # Trim in-place to avoid replacing the list object (thread-safety)
            if len(logs) > self._max_lines:
                del logs[: len(logs) - self._max_lines]
        except Exception:
            self.handleError(record)


class JobThreadFilter(logging.Filter):
    """Keep only log records emitted by a job's worker threads.

    Worker threads register themselves in ``job["log_threads"]`` (see
    ``_run_in_job_thread``). Threads spawned by the collector are plain
    ``threading.Thread`` instances with default ``Thread-N`` names; they are
    accepted too, which is only correct while a single job runs at a time
    (enforced by ``POST /pipelines/start``).
    """

    def __init__(self, job_dict: dict[str, Any]):
        super().__init__()
        self._job = job_dict

    def filter(self, record: logging.LogRecord) -> bool:
        if record.thread in self._job.get("log_threads", ()):
            return True
        return (record.threadName or "").startswith("Thread-")


def _run_in_job_thread(job: dict[str, Any], func, *args):
    """Run ``func`` in the current (executor) thread, registering it for log capture."""
    job.setdefault("log_threads", set()).add(threading.get_ident())
    return func(*args)


# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(
    title="SciLEx API",
    description="REST API for paper collection and analysis",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class APIKeyConfig(BaseModel):
    """API configuration for a single API."""

    api_name: str
    api_key: str | None = None
    mailto: str | None = None
    user_id: str | None = None
    user_mode: str | None = None
    token: str | None = None
    inst_token: str | None = None


class CollectionConfig(BaseModel):
    """Configuration for paper collection."""

    keywords: list[list[str]]
    bonus_keywords: list[str] | None = None
    years: list[int]
    apis: list[str]
    collect_name: str
    semantic_scholar_mode: str | None = "regular"
    aggregate_get_citations: bool | None = True
    output_dir: str | None = None
    enable_enrichment: bool = False

    @field_validator("collect_name")
    @classmethod
    def _validate_collect_name(cls, value: str) -> str:
        """Reject names that could escape the output directory."""
        _check_collection_name(value)
        return value


class FilterConfig(BaseModel):
    """Configuration for filtering papers."""

    enable_itemtype_filter: bool | None = False
    allowed_item_types: list[str] | None = None
    apply_relevance_ranking: bool | None = True
    max_papers: int | None = None
    min_abstract_words: int | None = 50
    max_abstract_words: int | None = 1000


class QualityFilters(BaseModel):
    """Quality filtering settings."""

    enable_text_filter: bool | None = True
    min_abstract_words: int | None = 50
    max_abstract_words: int | None = 1000
    enable_itemtype_bypass: bool | None = True
    enable_itemtype_filter: bool | None = False
    allowed_item_types: list[str] | None = None
    apply_relevance_ranking: bool | None = True
    max_papers: int | None = None


class PipelineRequest(BaseModel):
    """Request for running the full pipeline."""

    collection_config: CollectionConfig
    api_config: dict[str, dict[str, Any]] | None = None  # None: use server-side file
    filter_config: FilterConfig | None = None
    quality_filters: QualityFilters | None = None


class ExportRequest(BaseModel):
    """Request to export results."""

    collect_name: str
    format: str = "csv"  # csv, bibtex, json


class PipelineStatus(BaseModel):
    """Status of a running pipeline."""

    id: str
    status: str  # "running", "completed", "failed"
    progress: int  # 0-100
    message: str
    output_path: str | None = None
    error: str | None = None


# ============================================================================
# GLOBAL STATE (In production, use a proper job queue like Celery)
# ============================================================================

pipeline_jobs: dict[str, dict[str, Any]] = {}
output_dir = DEFAULT_OUTPUT_DIR


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


ACTIVE_JOB_STATUSES = ("pending", "running", "cancelling")
TERMINAL_JOB_STATUSES = ("completed", "failed", "cancelled")
_status_lock = threading.Lock()


def _set_status(job: dict[str, Any], new_status: str) -> bool:
    """Atomically move ``job`` to ``new_status`` if the transition is allowed.

    Terminal states (completed/failed/cancelled) are never left, and a job
    that is cancelling never goes back to running.

    Returns:
        True if the status was changed, False if the transition was refused.
    """
    with _status_lock:
        current = job.get("status")
        if current in TERMINAL_JOB_STATUSES:
            return False
        if current == "cancelling" and new_status in ("pending", "running"):
            return False
        job["status"] = new_status
        return True


def _cancel_if_requested(
    job: dict[str, Any], cancel_event: threading.Event | None, message: str
) -> bool:
    """Mark the job cancelled and return True if cancellation was requested."""
    if cancel_event is None or not cancel_event.is_set():
        return False
    _set_status(job, "cancelled")
    job["message"] = message
    return True


def _check_collection_name(name: str) -> None:
    """Raise ValueError if ``name`` is not a plain directory name."""
    if (
        not name
        or not name.strip()
        or "/" in name
        or "\\" in name
        or "\x00" in name
        or ".." in name
        or name in (".", "..")
    ):
        raise ValueError("Invalid collection name")


def _safe_collection_dir(name: str, root: str | os.PathLike | None = None) -> Path:
    """Return the directory of collection ``name`` under the output root.

    Args:
        name: Collection name supplied by the client.
        root: Output root (defaults to the module-level ``output_dir``).

    Returns:
        Path of the collection directory (not guaranteed to exist).

    Raises:
        HTTPException: 400 if the name is not a plain directory name or the
            resolved path escapes the output root.
    """
    try:
        _check_collection_name(name)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid collection name") from None

    root_path = Path(root if root is not None else output_dir)
    collection_path = root_path / name
    try:
        collection_path.resolve().relative_to(root_path.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid collection path") from None
    return collection_path


def _collection_has_active_job(name: str) -> bool:
    """Return True if a pending/running/cancelling job targets ``name``."""
    return any(
        job["status"] in ACTIVE_JOB_STATUSES
        and job.get("config", {}).get("collect_name") == name
        for job in list(pipeline_jobs.values())
    )


def get_api_config_path() -> Path:
    """Get path to API configuration file."""
    return PROJECT_ROOT / "scilex" / "api.config.yml"


def get_main_config_path() -> Path:
    """Get path to main SciLEx configuration file."""
    return PROJECT_ROOT / "scilex" / "scilex.config.yml"


def load_api_config() -> dict[str, Any]:
    """Load API configuration from file."""
    config_path = get_api_config_path()
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_api_config(config: dict[str, Any]) -> None:
    """Save API configuration to file."""
    config_path = get_api_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    # Create with owner-only permissions from the start (file holds secrets)
    file_descriptor = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(file_descriptor, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    os.chmod(config_path, 0o600)  # also tighten a pre-existing file


def save_main_config(config: dict[str, Any]) -> None:
    """Save main SciLEx configuration to file."""
    config_path = get_main_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def generate_job_id() -> str:
    """Generate a unique job ID."""
    return f"job_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"


async def run_collection_task(
    job_id: str,
    main_config: dict[str, Any],
    api_config: dict[str, Any],
    cancel_event: threading.Event | None = None,
) -> None:
    """Run the collection task in background."""
    job = pipeline_jobs[job_id]

    # Attach log handler to capture pipeline logs
    log_handler = JobLogHandler(job)
    log_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    log_handler.addFilter(JobThreadFilter(job))
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)

    try:
        _set_status(job, "running")  # refused if cancelled before start
        job["phase"] = "initializing"
        job["progress"] = 10
        job["message"] = "Starting collection..."

        if _cancel_if_requested(job, cancel_event, "Pipeline cancelled before start."):
            return

        # Ensure output directory exists
        os_output_dir = main_config.get("output_dir", output_dir)
        os.makedirs(os_output_dir, exist_ok=True)

        # Save config snapshot
        config_path = os.path.join(os_output_dir, "config_used.yml")
        with open(config_path, "w") as f:
            yaml.dump(main_config, f)

        job["progress"] = 20
        job["phase"] = "collecting"
        job["message"] = "Configuration saved, starting API collection..."

        # Ensure aggregate_collect can resolve runtime config from scilex/scilex.config.yml
        save_main_config(main_config)

        # Progress callback: maps collection progress to 20-70% range
        def on_collection_progress(api_stats, completed, total):
            ratio = completed / max(total, 1)
            job["progress"] = 20 + int(ratio * 50)
            job["message"] = f"Collecting papers... {completed}/{total} queries done"
            job["api_stats"] = {k: dict(v) for k, v in api_stats.items()}

        # Run collection with progress callback and cancel event
        collector = CollectCollection(
            main_config,
            api_config,
            progress_callback=on_collection_progress,
            cancel_event=cancel_event,
        )
        # Offload blocking call to thread pool so event loop stays responsive
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, _run_in_job_thread, job, collector.create_collects_jobs
        )

        # Check if cancelled during collection
        if _cancel_if_requested(
            job, cancel_event, "Pipeline cancelled during collection."
        ):
            return

        job["progress"] = 75
        job["phase"] = "aggregating"
        job["message"] = "Collection completed, aggregating results..."

        # Run aggregation via orchestrator (no sys.argv hack)
        from scilex.config import SciLExConfig
        from scilex.pipeline.orchestrator import AggregationOptions, run_aggregation

        agg_config = SciLExConfig.from_dicts(main_config, api_config)
        agg_options = AggregationOptions(
            skip_citations=not main_config.get("aggregate_get_citations", True),
            workers=3,
        )

        def _on_agg_progress(phase, pct, message):
            # Map aggregation 0-100 into job's 75-85 range
            job["progress"] = 75 + int(pct * 0.10)
            job["message"] = message

        await loop.run_in_executor(
            None,
            _run_in_job_thread,
            job,
            run_aggregation,
            agg_config,
            agg_options,
            _on_agg_progress,
        )

        # Check if cancelled during aggregation
        if _cancel_if_requested(
            job, cancel_event, "Pipeline cancelled after aggregation."
        ):
            return

        # Load filtering summary if available
        collect_name = main_config.get("collect_name", "collection")
        collect_dir = _safe_collection_dir(collect_name, os_output_dir)
        summary_path = collect_dir / "filtering_summary.json"
        if summary_path.exists():
            with open(summary_path) as f:
                job["filtering_summary"] = json.load(f)

        job["progress"] = 85
        job["message"] = "Aggregation completed."

        # Optional: HuggingFace enrichment
        if main_config.get("enable_enrichment", False):
            if _cancel_if_requested(
                job, cancel_event, "Pipeline cancelled before enrichment."
            ):
                return
            job["progress"] = 88
            job["phase"] = "enriching"
            job["message"] = "Running HuggingFace enrichment..."

            def on_enrichment_progress(processed, total, stats):
                ratio = processed / max(total, 1)
                job["progress"] = 88 + int(ratio * 7)  # Maps to 88-95% range
                matched = stats.get("matched", 0)
                job["message"] = (
                    f"Enriching papers... {processed}/{total} ({matched} matched)"
                )

            sys.argv = ["enrich"]
            from scilex.enrich_with_hf import main as enrich_main

            await loop.run_in_executor(
                None,
                _run_in_job_thread,
                job,
                lambda: enrich_main(progress_callback=on_enrichment_progress),
            )

        if _cancel_if_requested(
            job, cancel_event, "Pipeline cancelled before finalizing."
        ):
            return

        job["progress"] = 95
        job["phase"] = "completed"
        job["message"] = (
            "Enrichment completed."
            if main_config.get("enable_enrichment")
            else "Preparing output..."
        )

        # Prepare output
        csv_path = collect_dir / "aggregated_results.csv"

        if csv_path.exists():
            job["output_path"] = str(csv_path)
            df = pd.read_csv(csv_path, delimiter=";")

            # Derive year from date if year column is missing
            if "year" not in df.columns and "date" in df.columns:
                df["year"] = pd.to_datetime(df["date"], errors="coerce").dt.year

            job["stats"] = {
                "total_papers": len(df),
                "by_year": (
                    df["year"]
                    .dropna()
                    .astype(int)
                    .value_counts()
                    .sort_index()
                    .to_dict()
                    if "year" in df.columns
                    else {}
                ),
                "by_source": (
                    df["archive"].value_counts().to_dict()
                    if "archive" in df.columns
                    else {}
                ),
            }

        if _set_status(job, "completed"):
            job["progress"] = 100
            job["message"] = "Pipeline completed successfully!"

    except Exception as e:
        logger.error(f"Pipeline job {job_id} failed: {str(e)}", exc_info=True)
        if _set_status(job, "failed"):
            job["error"] = str(e)
            job["message"] = f"Error: {str(e)}"
    finally:
        root_logger.removeHandler(log_handler)


# ============================================================================
# API ENDPOINTS
# ============================================================================


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "SciLEx API",
        "version": "1.0.0",
        "description": "FastAPI backend for SciLEx paper collection and analysis",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# ============================================================================
# CONFIGURATION ENDPOINTS
# ============================================================================


@app.get("/api-config")
async def get_api_config():
    """Get current API configuration (without sensitive data)."""
    try:
        config = load_api_config()
        # Remove sensitive API keys
        safe_config = {}
        for api_name, api_settings in config.items():
            safe_config[api_name] = {}
            if isinstance(api_settings, dict):
                for key in api_settings:
                    if key in ["api_key", "token", "user_id", "inst_token"]:
                        safe_config[api_name][key] = "***CONFIGURED***"
                    else:
                        safe_config[api_name][key] = api_settings[key]

        return {"config": safe_config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api-config")
async def update_api_config(api_key_config: APIKeyConfig):
    """Update API configuration."""
    try:
        config = load_api_config()

        if api_key_config.api_name not in config:
            config[api_key_config.api_name] = {}

        # Update configuration with provided values.
        # Empty string clears the field.
        update_dict = api_key_config.model_dump(
            exclude_unset=True, exclude={"api_name"}
        )
        for key, value in update_dict.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                config[api_key_config.api_name].pop(key, None)
            else:
                config[api_key_config.api_name][key] = value

        if not config[api_key_config.api_name]:
            config.pop(api_key_config.api_name, None)

        save_api_config(config)
        return {
            "message": f"API configuration for {api_key_config.api_name} updated",
            "api_name": api_key_config.api_name,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.delete("/api-config/{api_name}/{field_name}")
async def delete_api_config_field(api_name: str, field_name: str):
    """Delete a specific API configuration field (e.g., api_key, token)."""
    allowed_fields = {
        "api_key",
        "mailto",
        "user_id",
        "user_mode",
        "token",
        "inst_token",
    }
    if field_name not in allowed_fields:
        raise HTTPException(status_code=400, detail="Unsupported field name")

    try:
        config = load_api_config()
        if api_name not in config or not isinstance(config[api_name], dict):
            raise HTTPException(status_code=404, detail="API configuration not found")

        if field_name not in config[api_name]:
            raise HTTPException(status_code=404, detail="Field not found")

        config[api_name].pop(field_name, None)
        if not config[api_name]:
            config.pop(api_name, None)

        save_api_config(config)
        return {
            "message": f"Deleted {field_name} from {api_name}",
            "api_name": api_name,
            "field_name": field_name,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/available-apis")
async def get_available_apis():
    """Get list of available APIs."""
    available_apis = [
        {
            "name": "SemanticScholar",
            "description": "Semantic Scholar - Free API with optional premium tier",
            "requires_key": True,
            "free_tier": True,
        },
        {
            "name": "OpenAlex",
            "description": "OpenAlex - Free open access database of research",
            "requires_key": False,
            "free_tier": True,
        },
        {
            "name": "Arxiv",
            "description": "arXiv - Preprints of scientific papers",
            "requires_key": False,
            "free_tier": True,
        },
        {
            "name": "PubMed",
            "description": "PubMed - Biomedical literature (35M+ papers)",
            "requires_key": False,
            "free_tier": True,
        },
        {
            "name": "DBLP",
            "description": "DBLP - Computer Science bibliography",
            "requires_key": False,
            "free_tier": True,
        },
        {
            "name": "HAL",
            "description": "HAL - French multidisciplinary open access archive",
            "requires_key": False,
            "free_tier": True,
        },
        {
            "name": "PubMedCentral",
            "description": "PubMed Central - Free full-text biomedical articles",
            "requires_key": False,
            "free_tier": True,
        },
        {
            "name": "Istex",
            "description": "ISTEX - French scientific full-text archive",
            "requires_key": False,
            "free_tier": True,
        },
        {
            "name": "IEEE",
            "description": "IEEE Xplore - IEEE digital library",
            "requires_key": True,
            "free_tier": False,
        },
        {
            "name": "Elsevier",
            "description": "ScienceDirect - Elsevier journals",
            "requires_key": True,
            "free_tier": False,
        },
        {
            "name": "Springer",
            "description": "Springer - Springer journals and books",
            "requires_key": True,
            "free_tier": False,
        },
    ]
    return {"apis": available_apis}


# ============================================================================
# COLLECTION ENDPOINTS
# ============================================================================


@app.post("/pipelines/start")
async def start_pipeline(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Start a new collection pipeline (one job at a time)."""
    # Jobs share global state (scilex.config.yml, sys.argv, root logger), so
    # concurrent runs would corrupt each other. No await between this check
    # and the job insertion below: the check-and-insert is atomic on the loop.
    if any(job["status"] in ACTIVE_JOB_STATUSES for job in pipeline_jobs.values()):
        raise HTTPException(
            status_code=409, detail="Another pipeline job is already running"
        )
    try:
        job_id = generate_job_id()

        # Keys stay server-side unless a client explicitly supplies its own
        api_config = (
            request.api_config if request.api_config is not None else load_api_config()
        )

        # Prepare main configuration
        main_config = {
            "keywords": request.collection_config.keywords,
            "years": request.collection_config.years,
            "apis": request.collection_config.apis,
            "collect_name": request.collection_config.collect_name,
            "output_dir": request.collection_config.output_dir or output_dir,
            "collect": True,
            "aggregate_get_citations": request.collection_config.aggregate_get_citations,
            "enable_enrichment": request.collection_config.enable_enrichment,
        }

        if request.collection_config.semantic_scholar_mode:
            main_config["semantic_scholar_mode"] = (
                request.collection_config.semantic_scholar_mode
            )

        if request.quality_filters:
            main_config["quality_filters"] = request.quality_filters.model_dump(
                exclude_unset=True
            )

        # Initialize job with cancel event
        cancel_event = threading.Event()
        pipeline_jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "phase": "initializing",
            "progress": 0,
            "message": "Initializing...",
            "created_at": datetime.now().isoformat(),
            "started_at": time.time(),
            "config": main_config,
            "cancel_event": cancel_event,
            "logs": [],
            "enrichment_enabled": main_config.get("enable_enrichment", False),
        }

        # Run collection in background
        background_tasks.add_task(
            run_collection_task,
            job_id,
            main_config,
            api_config,
            cancel_event,
        )

        return {
            "job_id": job_id,
            "message": "Pipeline started",
            "status": "pending",
        }

    except Exception as e:
        logger.error(f"Failed to start pipeline: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/pipelines/{job_id}/status")
async def get_pipeline_status(job_id: str):
    """Get status of a pipeline job."""
    if job_id not in pipeline_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = pipeline_jobs[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "phase": job.get("phase", "initializing"),
        "progress": job["progress"],
        "message": job["message"],
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "error": job.get("error"),
        "stats": job.get("stats"),
        "api_stats": job.get("api_stats"),
        "logs": job.get("logs", []),
        "filtering_summary": job.get("filtering_summary"),
        "enrichment_enabled": job.get("enrichment_enabled", False),
    }


@app.post("/pipelines/{job_id}/cancel")
async def cancel_pipeline(job_id: str):
    """Cancel a running pipeline job."""
    if job_id not in pipeline_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = pipeline_jobs[job_id]
    if job["status"] in TERMINAL_JOB_STATUSES:
        return {"message": f"Job already finished ({job['status']})", "job_id": job_id}
    if job["status"] not in ("pending", "running"):
        raise HTTPException(
            status_code=400, detail=f"Job is not running (status: {job['status']})"
        )

    cancel_event = job.get("cancel_event")
    if cancel_event:
        cancel_event.set()

    if not _set_status(job, "cancelling"):
        return {"message": f"Job already finished ({job['status']})", "job_id": job_id}
    job["message"] = "Cancellation requested, finishing current queries..."
    return {"message": "Cancellation requested", "job_id": job_id}


@app.get("/pipelines")
async def list_pipelines():
    """List all pipeline jobs."""
    jobs = [
        {
            "job_id": job_id,
            "status": job["status"],
            "progress": job["progress"],
            "created_at": job.get("created_at"),
        }
        for job_id, job in pipeline_jobs.items()
    ]
    return {"jobs": jobs}


# ============================================================================
# RESULTS ENDPOINTS
# ============================================================================


@app.get("/results/{collect_name}")
async def get_results(collect_name: str, limit: int = 100, skip: int = 0):
    """Get aggregated results for a collection."""
    try:
        csv_path = _safe_collection_dir(collect_name) / "aggregated_results.csv"

        if not csv_path.exists():
            raise HTTPException(status_code=404, detail="Results not found")

        df = pd.read_csv(csv_path, delimiter=";")

        # Apply limit and skip
        total = len(df)
        df = df.iloc[skip : skip + limit]

        # Convert to dict, handling NaN values
        records = df.fillna("").to_dict(orient="records")

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "records": records,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/results/{collect_name}/stats")
async def get_results_stats(collect_name: str):
    """Get statistics about results."""
    try:
        csv_path = _safe_collection_dir(collect_name) / "aggregated_results.csv"

        if not csv_path.exists():
            raise HTTPException(status_code=404, detail="Results not found")

        df = pd.read_csv(csv_path, delimiter=";")

        # Derive year from date if year column is missing
        if "year" not in df.columns and "date" in df.columns:
            df["year"] = pd.to_datetime(df["date"], errors="coerce").dt.year

        stats = {
            "total_papers": len(df),
        }

        if "year" in df.columns:
            stats["by_year"] = df["year"].value_counts().sort_index().to_dict()

        if "archive" in df.columns:
            stats["by_source"] = df["archive"].value_counts().to_dict()

        if "nb_citation" in df.columns:
            stats["avg_citations"] = float(df["nb_citation"].mean())
            stats["max_citations"] = int(df["nb_citation"].max())

        return {"stats": stats}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/export")
async def export_results(request: ExportRequest):
    """Export results in different formats."""
    try:
        collection_dir = _safe_collection_dir(request.collect_name)
        csv_path = collection_dir / "aggregated_results.csv"

        if not csv_path.exists():
            raise HTTPException(status_code=404, detail="Results not found")

        if request.format == "csv":
            return FileResponse(
                csv_path,
                media_type="text/csv",
                filename=f"{request.collect_name}_results.csv",
            )

        elif request.format == "bibtex":
            # Try to generate BibTeX export
            bibtex_path = collection_dir / "aggregated_results.bib"
            if bibtex_path.exists():
                return FileResponse(
                    bibtex_path,
                    media_type="application/x-bibtex",
                    filename=f"{request.collect_name}_results.bib",
                )
            else:
                raise HTTPException(
                    status_code=404,
                    detail="BibTeX export not found. Run bibtex export.",
                )

        elif request.format == "json":
            df = pd.read_csv(csv_path, delimiter=";")
            json_path = collection_dir / "results_temp.json"
            df.to_json(json_path, orient="records")
            return FileResponse(
                json_path,
                media_type="application/json",
                filename=f"{request.collect_name}_results.json",
            )

        else:
            raise HTTPException(status_code=400, detail="Unsupported format")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/collections")
async def list_collections():
    """List all available collection directories."""
    try:
        if not os.path.exists(output_dir):
            return {"collections": []}

        collections = []
        for item in os.listdir(output_dir):
            item_path = os.path.join(output_dir, item)
            if os.path.isdir(item_path) and item not in [
                "text_to_sparql",
                "text2sparql",
            ]:
                csv_path = os.path.join(item_path, "aggregated_results.csv")
                if os.path.exists(csv_path):
                    df = pd.read_csv(csv_path, delimiter=";")
                    collections.append(
                        {
                            "name": item,
                            "papers_count": len(df),
                            "created_at": os.path.getctime(item_path),
                        }
                    )

        return {
            "collections": sorted(
                collections, key=lambda x: x["created_at"], reverse=True
            )
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.delete("/collections/{name}")
async def delete_collection(name: str):
    """Delete a collection directory with path traversal protection."""

    collection_path = _safe_collection_dir(name)

    if _collection_has_active_job(name):
        raise HTTPException(
            status_code=409, detail="Collection has a running pipeline job"
        )

    if not collection_path.is_dir():
        raise HTTPException(status_code=404, detail="Collection not found")

    try:
        shutil.rmtree(collection_path)
        return {"message": f"Collection '{name}' deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# ============================================================================
# FILTER ENDPOINTS
# ============================================================================


@app.post("/filter/{collect_name}")
async def filter_results(collect_name: str, filters: FilterConfig):
    """Apply filters to results and return filtered subset."""
    try:
        csv_path = _safe_collection_dir(collect_name) / "aggregated_results.csv"

        if not csv_path.exists():
            raise HTTPException(status_code=404, detail="Results not found")

        df = pd.read_csv(csv_path, delimiter=";")

        # Apply filters using shared post-filter module
        from scilex.pipeline.post_filter import apply_post_filters

        df = apply_post_filters(df, filters.model_dump())

        return {
            "total": len(df),
            "records": df.fillna("").to_dict(orient="records"),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
