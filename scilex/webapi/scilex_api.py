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
from pydantic import BaseModel

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
    api_config: dict[str, dict[str, Any]]
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
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


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
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)

    try:
        job["status"] = "running"
        job["phase"] = "initializing"
        job["progress"] = 10
        job["message"] = "Starting collection..."

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
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, collector.create_collects_jobs)

        # Check if cancelled during collection
        if cancel_event and cancel_event.is_set():
            job["status"] = "cancelled"
            job["message"] = "Pipeline cancelled during collection."
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
            None, run_aggregation, agg_config, agg_options, _on_agg_progress
        )

        # Check if cancelled during aggregation
        if cancel_event and cancel_event.is_set():
            job["status"] = "cancelled"
            job["message"] = "Pipeline cancelled after aggregation."
            return

        # Load filtering summary if available
        collect_name = main_config.get("collect_name", "collection")
        summary_path = os.path.join(
            os_output_dir, collect_name, "filtering_summary.json"
        )
        if os.path.exists(summary_path):
            with open(summary_path) as f:
                job["filtering_summary"] = json.load(f)

        job["progress"] = 85
        job["message"] = "Aggregation completed."

        # Optional: HuggingFace enrichment
        if main_config.get("enable_enrichment", False):
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
                None, lambda: enrich_main(progress_callback=on_enrichment_progress)
            )

        job["progress"] = 95
        job["phase"] = "completed"
        job["message"] = (
            "Enrichment completed."
            if main_config.get("enable_enrichment")
            else "Preparing output..."
        )

        # Prepare output
        collect_dir = os.path.join(
            os_output_dir, main_config.get("collect_name", "collection")
        )
        csv_path = os.path.join(collect_dir, "aggregated_results.csv")

        if os.path.exists(csv_path):
            job["output_path"] = csv_path
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

        job["progress"] = 100
        job["status"] = "completed"
        job["message"] = "Pipeline completed successfully!"

    except Exception as e:
        logger.error(f"Pipeline job {job_id} failed: {str(e)}", exc_info=True)
        job["status"] = "failed"
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
        update_dict = api_key_config.dict(exclude_unset=True, exclude={"api_name"})
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
    allowed_fields = {"api_key", "user_id", "user_mode", "token", "inst_token"}
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
    """Start a new collection pipeline."""
    try:
        job_id = generate_job_id()

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
            main_config["quality_filters"] = request.quality_filters.dict(
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
            request.api_config,
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
    if job["status"] in ("completed", "failed", "cancelled"):
        return {"message": f"Job already finished ({job['status']})", "job_id": job_id}
    if job["status"] not in ("pending", "running"):
        raise HTTPException(
            status_code=400, detail=f"Job is not running (status: {job['status']})"
        )

    cancel_event = job.get("cancel_event")
    if cancel_event:
        cancel_event.set()

    job["status"] = "cancelling"
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
        csv_path = os.path.join(output_dir, collect_name, "aggregated_results.csv")

        if not os.path.exists(csv_path):
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
        csv_path = os.path.join(output_dir, collect_name, "aggregated_results.csv")

        if not os.path.exists(csv_path):
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
        csv_path = os.path.join(
            output_dir, request.collect_name, "aggregated_results.csv"
        )

        if not os.path.exists(csv_path):
            raise HTTPException(status_code=404, detail="Results not found")

        if request.format == "csv":
            return FileResponse(
                csv_path,
                media_type="text/csv",
                filename=f"{request.collect_name}_results.csv",
            )

        elif request.format == "bibtex":
            # Try to generate BibTeX export
            bibtex_path = os.path.join(
                output_dir, request.collect_name, "aggregated_results.bib"
            )
            if os.path.exists(bibtex_path):
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
            json_path = os.path.join(
                output_dir, request.collect_name, "results_temp.json"
            )
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

    # Validate name — must not be empty or contain path separators/special components
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid collection name")

    collection_path = Path(output_dir) / name

    # Ensure the resolved path is actually under output_dir
    try:
        collection_path.resolve().relative_to(Path(output_dir).resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid collection path") from None

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
        csv_path = os.path.join(output_dir, collect_name, "aggregated_results.csv")

        if not os.path.exists(csv_path):
            raise HTTPException(status_code=404, detail="Results not found")

        df = pd.read_csv(csv_path, delimiter=";")

        # Apply filters using shared post-filter module
        from scilex.pipeline.post_filter import apply_post_filters

        df = apply_post_filters(df, filters.dict())

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
