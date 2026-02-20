#!/usr/bin/env python3
"""HuggingFace Hub API client with caching and rate limiting.

This module provides a clean interface to HuggingFace Hub API for:
- Searching models by paper title
- Searching datasets by paper title
- Extracting metadata from model/dataset cards
- Caching results to avoid redundant API calls
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import requests
from huggingface_hub import HfApi
from ratelimit import limits, sleep_and_retry


class HFCache:
    """SQLite cache for HuggingFace API responses (30-day TTL)."""

    def __init__(self, cache_path: str = "output/hf_cache.db"):
        """Initialize cache with WAL mode for thread safety.

        Args:
            cache_path: Path to SQLite cache database
        """
        self.cache_path = cache_path
        # Create output directory if it doesn't exist
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create cache tables if not exist."""
        conn = sqlite3.connect(self.cache_path)
        conn.execute("PRAGMA journal_mode=WAL")  # WAL mode for thread safety

        # Create models cache table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hf_models (
                paper_title TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                cached_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL
            )
            """
        )

        # Create datasets cache table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hf_datasets (
                paper_title TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                cached_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL
            )
            """
        )

        # Create papers cache table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hf_papers (
                paper_query TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                cached_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL
            )
            """
        )

        # Create index for faster expiration cleanup
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_models_expires ON hf_models(expires_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_datasets_expires ON hf_datasets(expires_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_papers_expires ON hf_papers(expires_at)"
        )

        conn.commit()
        conn.close()

    def get_models(self, paper_title: str) -> list[dict] | None:
        """Retrieve cached models for paper title.

        Args:
            paper_title: Academic paper title

        Returns:
            List of model metadata dictionaries, or None if expired/not found
        """
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT result_json, expires_at
            FROM hf_models
            WHERE paper_title = ?
            """,
            (paper_title,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        result_json, expires_at_str = row

        # Check expiration
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now() >= expires_at:
            logging.debug(f"Cache expired for: {paper_title}")
            return None

        # Return cached results
        return json.loads(result_json)

    def cache_models(self, paper_title: str, models: list[dict], ttl_days: int = 30):
        """Cache models with configurable TTL.

        Args:
            paper_title: Academic paper title
            models: List of model metadata dictionaries
            ttl_days: Time-to-live in days (default: 30)
        """
        conn = sqlite3.connect(self.cache_path)

        now = datetime.now()
        expires_at = now + timedelta(days=ttl_days)

        conn.execute(
            """
            INSERT OR REPLACE INTO hf_models
            (paper_title, result_json, cached_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (paper_title, json.dumps(models), now.isoformat(), expires_at.isoformat()),
        )

        conn.commit()
        conn.close()

    def get_datasets(self, paper_title: str) -> list[dict] | None:
        """Retrieve cached datasets for paper title.

        Args:
            paper_title: Academic paper title

        Returns:
            List of dataset metadata dictionaries, or None if expired/not found
        """
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT result_json, expires_at
            FROM hf_datasets
            WHERE paper_title = ?
            """,
            (paper_title,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        result_json, expires_at_str = row

        # Check expiration
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now() >= expires_at:
            logging.debug(f"Cache expired for: {paper_title}")
            return None

        # Return cached results
        return json.loads(result_json)

    def cache_datasets(
        self, paper_title: str, datasets: list[dict], ttl_days: int = 30
    ):
        """Cache datasets with configurable TTL.

        Args:
            paper_title: Academic paper title
            datasets: List of dataset metadata dictionaries
            ttl_days: Time-to-live in days (default: 30)
        """
        conn = sqlite3.connect(self.cache_path)

        now = datetime.now()
        expires_at = now + timedelta(days=ttl_days)

        conn.execute(
            """
            INSERT OR REPLACE INTO hf_datasets
            (paper_title, result_json, cached_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                paper_title,
                json.dumps(datasets),
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )

        conn.commit()
        conn.close()

    def get_papers(self, query: str) -> list[dict] | None:
        """Retrieve cached papers for query (title or paper ID).

        Args:
            query: Paper title or identifier to search for

        Returns:
            List of paper metadata dictionaries, or None if expired/not found
        """
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT result_json, expires_at
            FROM hf_papers
            WHERE paper_query = ?
            """,
            (query,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        result_json, expires_at = row

        # Check expiration
        expires_at_dt = datetime.fromisoformat(expires_at)
        if datetime.now() > expires_at_dt:
            return None

        return json.loads(result_json)

    def cache_papers(self, query: str, papers: list[dict], ttl_days: int = 30):
        """Cache papers with configurable TTL.

        Args:
            query: Paper title or identifier used for search
            papers: List of paper metadata dictionaries
            ttl_days: Time-to-live in days (default: 30)
        """
        conn = sqlite3.connect(self.cache_path)

        now = datetime.now()
        expires_at = now + timedelta(days=ttl_days)

        conn.execute(
            """
            INSERT OR REPLACE INTO hf_papers
            (paper_query, result_json, cached_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                query,
                json.dumps(papers),
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )

        conn.commit()
        conn.close()

    def cleanup_expired(self):
        """Remove expired cache entries."""
        conn = sqlite3.connect(self.cache_path)

        now = datetime.now().isoformat()

        # Clean models
        cursor = conn.execute(
            "DELETE FROM hf_models WHERE expires_at < ?",
            (now,),
        )
        models_deleted = cursor.rowcount

        # Clean datasets
        cursor = conn.execute(
            "DELETE FROM hf_datasets WHERE expires_at < ?",
            (now,),
        )
        datasets_deleted = cursor.rowcount

        # Clean papers
        cursor = conn.execute(
            "DELETE FROM hf_papers WHERE expires_at < ?",
            (now,),
        )
        papers_deleted = cursor.rowcount

        conn.commit()
        conn.close()

        if models_deleted + datasets_deleted + papers_deleted > 0:
            logging.info(
                f"Cleaned {models_deleted} model + {datasets_deleted} dataset + {papers_deleted} paper cache entries"
            )


class HFClient:
    """Client for HuggingFace Hub API with intelligent caching.

    Attributes:
        api: HfApi instance (from huggingface_hub)
        token: Optional HF token for authentication
        cache: HFCache instance for persistent caching
        cache_ttl_days: Cache time-to-live in days
    """

    def __init__(
        self,
        token: str | None = None,
        cache_path: str = "output/hf_cache.db",
        cache_ttl_days: int = 30,
    ):
        """Initialize HuggingFace client.

        Args:
            token: Optional HF token (improves rate limits)
            cache_path: Path to SQLite cache database
            cache_ttl_days: Cache expiration in days (default: 30)
        """
        self.api = HfApi(token=token)
        self.token = token
        self.cache = HFCache(cache_path)
        self.cache_ttl_days = cache_ttl_days

    @sleep_and_retry
    @limits(calls=5, period=1)  # 5 calls per second (HF Hub default)
    def search_models_by_title(self, paper_title: str, limit: int = 10) -> list[dict]:
        """Search HuggingFace models by paper title.

        Strategy:
        1. Check cache first (30-day TTL)
        2. If cache miss, query HF Hub API
        3. Cache results before returning

        Args:
            paper_title: Academic paper title to search for
            limit: Maximum models to return (default: 10)

        Returns:
            List of model metadata dictionaries
        """
        # Check cache
        cached = self.cache.get_models(paper_title)
        if cached is not None:
            logging.debug(f"💾 Cache hit for models: {paper_title[:50]}...")
            return cached

        # API call (rate-limited)
        logging.debug(f"🔗 API call for models: {paper_title[:50]}...")
        try:
            # Use HfApi.list_models() with search parameter
            models = list(
                self.api.list_models(
                    search=paper_title, limit=limit, sort="downloads", direction=-1
                )
            )

            # Convert to dict format
            results = [self._model_to_dict(m) for m in models]

            # Cache results
            self.cache.cache_models(paper_title, results, ttl_days=self.cache_ttl_days)

            return results
        except Exception as e:
            logging.error(f"HF API error for models: {e}")
            return []

    @sleep_and_retry
    @limits(calls=5, period=1)
    def search_datasets_by_title(self, paper_title: str, limit: int = 10) -> list[dict]:
        """Search HuggingFace datasets by paper title.

        Similar strategy to search_models_by_title but for datasets.

        Args:
            paper_title: Academic paper title to search for
            limit: Maximum datasets to return (default: 10)

        Returns:
            List of dataset metadata dictionaries
        """
        # Check cache
        cached = self.cache.get_datasets(paper_title)
        if cached is not None:
            logging.debug(f"💾 Cache hit for datasets: {paper_title[:50]}...")
            return cached

        # API call (rate-limited)
        logging.debug(f"🔗 API call for datasets: {paper_title[:50]}...")
        try:
            # Use HfApi.list_datasets() with search parameter
            datasets = list(
                self.api.list_datasets(
                    search=paper_title, limit=limit, sort="downloads"
                )
            )

            # Convert to dict format
            results = [self._dataset_to_dict(d) for d in datasets]

            # Cache results
            self.cache.cache_datasets(
                paper_title, results, ttl_days=self.cache_ttl_days
            )

            return results
        except Exception as e:
            logging.error(f"HF API error for datasets: {e}")
            return []

    @sleep_and_retry
    @limits(calls=5, period=1)
    def search_papers_by_title(self, paper_title: str, limit: int = 10) -> list[dict]:
        """Search HuggingFace Daily Papers by title using REST API.

        Uses the HuggingFace REST API /api/papers/search endpoint to find
        academic papers indexed on HF Daily Papers.

        Args:
            paper_title: Academic paper title to search for
            limit: Maximum papers to return (default: 10)

        Returns:
            List of paper metadata dictionaries with fields:
            - id: Paper ID (often arXiv ID)
            - title: Paper title
            - authors: List of author names
            - summary: Abstract
            - published_at: Publication date
        """
        # Check cache
        cached = self.cache.get_papers(paper_title)
        if cached is not None:
            logging.debug(f"💾 Cache hit for papers: {paper_title[:50]}...")
            return cached

        # API call (rate-limited) - Use REST API directly
        logging.debug(f"🔗 REST API call for papers: {paper_title[:50]}...")
        try:
            url = "https://huggingface.co/api/papers/search"
            params = {"q": paper_title}
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()

            papers_data = response.json()

            # Limit results
            papers_data = papers_data[:limit]

            # Convert to dict format
            results = [self._paper_to_dict(p) for p in papers_data]

            # Cache results
            self.cache.cache_papers(paper_title, results, ttl_days=self.cache_ttl_days)

            return results
        except requests.exceptions.RequestException as e:
            logging.error(f"HF Papers REST API error: {e}")
            return []
        except Exception as e:
            logging.error(f"HF API error for papers: {e}")
            return []

    @sleep_and_retry
    @limits(calls=5, period=1)
    def get_paper_info(self, paper_id: str) -> dict | None:
        """Get paper info including the paper's actual GitHub repo.

        Uses GET /api/papers/{paper_id} endpoint to fetch paper metadata
        that includes the paper's own GitHub repository (not citing repos).

        Args:
            paper_id: Paper ID (arXiv ID like "2307.03172")

        Returns:
            Dictionary with paper metadata:
            - githubRepo: Paper's actual GitHub repository URL
            - githubStars: Star count on GitHub
            - ai_keywords: AI-extracted keywords from paper
            - title, authors, summary, etc.
            Returns None if paper not found or error occurs.
        """
        logging.debug(f"🔗 REST API call for paper info: {paper_id}")
        try:
            url = f"https://huggingface.co/api/papers/{paper_id}"
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            return response.json()
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch paper info for {paper_id}: {e}")
            return None
        except Exception as e:
            logging.warning(f"Error fetching paper info for {paper_id}: {e}")
            return None

    @sleep_and_retry
    @limits(calls=5, period=1)
    def get_paper_linked_resources(self, paper_id: str) -> dict:
        """Get models and datasets that CITE this paper via REST API.

        Note: This returns repos that CITE the paper, not the paper's own repos.
        Use get_paper_info() to get the paper's actual GitHub repository.

        Args:
            paper_id: Paper ID from HF Papers API (e.g., arXiv ID like "2301.12345")

        Returns:
            Dictionary with:
            {
                "citing_models": [list of model dicts that cite this paper],
                "citing_datasets": [list of dataset dicts that cite this paper]
            }
        """
        results = {"citing_models": [], "citing_datasets": []}

        # Use REST API: GET /api/arxiv/{arxiv_id}/repos
        try:
            url = f"https://huggingface.co/api/arxiv/{paper_id}/repos"
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            repos_data = response.json()

            # Response is a dict with "models", "datasets", "spaces" keys
            # These are repos that CITE this paper, not the paper's own repos
            for model in repos_data.get("models", []):
                model_id = model.get("id", "")
                model_dict = {
                    "modelId": model_id,
                    "author": model.get("author"),
                    "tags": model.get("tags", []),
                    "pipeline_tag": model.get("pipeline_tag"),
                    "downloads": model.get("downloads", 0),
                    "likes": model.get("likes", 0),
                    "card_data": model.get("cardData", {}),
                }
                results["citing_models"].append(model_dict)

            for dataset in repos_data.get("datasets", []):
                dataset_id = dataset.get("id", "")
                dataset_dict = {
                    "datasetId": dataset_id,
                    "author": dataset.get("author"),
                    "tags": dataset.get("tags", []),
                    "downloads": dataset.get("downloads", 0),
                    "likes": dataset.get("likes", 0),
                    "card_data": dataset.get("cardData", {}),
                }
                results["citing_datasets"].append(dataset_dict)

        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch linked repos for paper {paper_id}: {e}")
        except Exception as e:
            logging.warning(
                f"Error fetching linked resources for paper {paper_id}: {e}"
            )

        return results

    def _model_to_dict(self, model_info) -> dict:
        """Convert HfApi ModelInfo object to dictionary.

        Args:
            model_info: ModelInfo object from huggingface_hub

        Returns:
            Dictionary with model metadata
        """
        return {
            "modelId": model_info.id,
            "author": model_info.author,
            "tags": model_info.tags if model_info.tags else [],
            "pipeline_tag": getattr(model_info, "pipeline_tag", None),
            "downloads": getattr(model_info, "downloads", 0),
            "likes": getattr(model_info, "likes", 0),
            "card_data": getattr(model_info, "card_data", {}),
        }

    def _dataset_to_dict(self, dataset_info) -> dict:
        """Convert HfApi DatasetInfo object to dictionary.

        Args:
            dataset_info: DatasetInfo object from huggingface_hub

        Returns:
            Dictionary with dataset metadata
        """
        return {
            "datasetId": dataset_info.id,
            "author": dataset_info.author,
            "tags": dataset_info.tags if dataset_info.tags else [],
            "downloads": getattr(dataset_info, "downloads", 0),
            "likes": getattr(dataset_info, "likes", 0),
            "card_data": getattr(dataset_info, "card_data", {}),
        }

    def _paper_to_dict(self, paper_info) -> dict:
        """Convert REST API paper response or PaperInfo object to dictionary.

        Handles both:
        - REST API dict responses from /api/papers/search
        - PaperInfo-like objects (fallback)

        Args:
            paper_info: Dict from REST API or PaperInfo object

        Returns:
            Dictionary with paper metadata
        """
        # Handle REST API dict response
        if isinstance(paper_info, dict):
            # REST API may nest paper data inside "paper" key
            paper_data = paper_info.get("paper", paper_info)

            # Extract authors from REST API format
            authors = []
            raw_authors = paper_data.get("authors", [])
            for author in raw_authors:
                if isinstance(author, dict):
                    # REST API format: {"_id": "...", "name": "...", ...}
                    name = author.get("name", author.get("fullname", "Unknown"))
                elif isinstance(author, str):
                    name = author
                else:
                    name = str(author)
                authors.append(name)

            # Extract date (REST API uses "publishedAt" or "published_at")
            published_at = paper_data.get("publishedAt", paper_data.get("published_at"))
            if published_at and hasattr(published_at, "isoformat"):
                published_at = published_at.isoformat()

            return {
                "id": paper_data.get("id", "unknown"),
                "title": paper_data.get("title", ""),
                "authors": authors,
                "summary": paper_data.get("summary", ""),
                "published_at": published_at,
            }

        # Handle PaperInfo-like object (fallback for library objects)
        authors = []
        raw_authors = getattr(paper_info, "authors", [])
        if raw_authors:
            for author in raw_authors:
                if isinstance(author, dict):
                    name = author.get("name", author.get("fullname", "Unknown"))
                elif isinstance(author, str):
                    name = author
                else:
                    name = str(author)
                authors.append(name)

        # Safe date extraction
        published_at = getattr(paper_info, "published_at", None)
        if published_at:
            if hasattr(published_at, "isoformat"):
                published_at = published_at.isoformat()
            else:
                published_at = str(published_at)

        return {
            "id": getattr(paper_info, "id", "unknown"),
            "title": getattr(paper_info, "title", ""),
            "authors": authors,
            "summary": getattr(paper_info, "summary", ""),
            "published_at": published_at,
        }
