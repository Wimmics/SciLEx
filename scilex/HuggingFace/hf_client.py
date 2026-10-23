#!/usr/bin/env python3
"""HuggingFace Hub API client with caching and rate limiting.

This module provides a clean interface to HuggingFace Hub API for:
- Searching models by paper title
- Searching papers (HF Daily Papers) and their linked resources
- Caching results to avoid redundant API calls

Rate limiting only applies to real network calls (never to cache hits).
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

    # Allowlist: table name -> key column (names kept for existing databases)
    TABLES = {"hf_models": "paper_title", "hf_papers": "paper_query"}

    def __init__(self, cache_path: str = "output/hf_cache.db"):
        """Initialize cache with WAL mode for thread safety.

        Args:
            cache_path: Path to SQLite cache database
        """
        self.cache_path = cache_path
        # Create output directory if it doesn't exist
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Open a connection that waits for concurrent writers."""
        return sqlite3.connect(self.cache_path, timeout=30)

    def _init_db(self):
        """Create cache tables if not exist."""
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")  # WAL mode for thread safety
            for table, key_column in self.TABLES.items():
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        {key_column} TEXT PRIMARY KEY,
                        result_json TEXT NOT NULL,
                        cached_at TIMESTAMP NOT NULL,
                        expires_at TIMESTAMP NOT NULL
                    )
                    """
                )
                # Index for faster expiration cleanup
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{table}_expires "
                    f"ON {table}(expires_at)"
                )
            conn.commit()
        finally:
            conn.close()

    def _get(self, table: str, key: str) -> list[dict] | None:
        """Return the cached payload for key, or None if absent/expired."""
        key_column = self.TABLES[table]
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT result_json, expires_at FROM {table} WHERE {key_column} = ?",
                (key,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return None

        result_json, expires_at_str = row
        if datetime.now() >= datetime.fromisoformat(expires_at_str):
            logging.debug(f"Cache expired for: {key}")
            return None

        return json.loads(result_json)

    def _set(self, table: str, key: str, payload: list[dict], ttl_days: int):
        """Store payload under key with a TTL in days."""
        key_column = self.TABLES[table]
        now = datetime.now()
        expires_at = now + timedelta(days=ttl_days)
        conn = self._connect()
        try:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {table}
                ({key_column}, result_json, cached_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    key,
                    json.dumps(payload, default=str),
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_models(self, paper_title: str) -> list[dict] | None:
        """Retrieve cached models for a key, or None if expired/not found."""
        return self._get("hf_models", paper_title)

    def cache_models(self, paper_title: str, models: list[dict], ttl_days: int = 30):
        """Cache models with configurable TTL (default: 30 days)."""
        self._set("hf_models", paper_title, models, ttl_days)

    def get_papers(self, query: str) -> list[dict] | None:
        """Retrieve cached papers for a key, or None if expired/not found."""
        return self._get("hf_papers", query)

    def cache_papers(self, query: str, papers: list[dict], ttl_days: int = 30):
        """Cache papers with configurable TTL (default: 30 days)."""
        self._set("hf_papers", query, papers, ttl_days)


@sleep_and_retry
@limits(calls=5, period=1)  # 5 calls per second (HF Hub default)
def _throttle() -> None:
    """Block until a network call is allowed (cache hits never call this)."""


def _normalize_cache_key(query: str, limit: int) -> str:
    """Normalize a query (strip, lowercase, collapse whitespace) and add limit."""
    return f"{' '.join(query.lower().split())}|limit={limit}"


def _card_data_to_dict(card_data) -> dict:
    """Convert huggingface_hub CardData (or None) to a JSON-serializable dict."""
    if card_data is None:
        return {}
    if isinstance(card_data, dict):
        return card_data
    if hasattr(card_data, "to_dict"):
        return card_data.to_dict()
    return {}


class HFClient:
    """Client for HuggingFace Hub API with intelligent caching.

    Attributes:
        api: HfApi instance (from huggingface_hub)
        token: Optional HF token for authentication
        cache: HFCache instance for persistent caching
        cache_ttl_days: Cache time-to-live in days
    """

    REST_BASE_URL = "https://huggingface.co/api"

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

    def _rest_get(self, path: str, params: dict | None = None):
        """Rate-limited GET on the HF REST API; returns parsed JSON.

        Raises:
            requests.exceptions.RequestException: On network/HTTP errors.
        """
        _throttle()
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        response = requests.get(
            f"{self.REST_BASE_URL}/{path}",
            params=params,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _hub_call(self, function, *args, **kwargs):
        """Rate-limited call into huggingface_hub."""
        _throttle()
        return function(*args, **kwargs)

    def search_models_by_title(self, paper_title: str, limit: int = 10) -> list[dict]:
        """Search HuggingFace models by paper title.

        Strategy:
        1. Check cache first (30-day TTL)
        2. If cache miss, query HF Hub API (rate-limited)
        3. Cache results before returning

        Args:
            paper_title: Academic paper title to search for
            limit: Maximum models to return (default: 10)

        Returns:
            List of model metadata dictionaries
        """
        cache_key = _normalize_cache_key(paper_title, limit)
        cached = self.cache.get_models(cache_key)
        if cached is not None:
            logging.debug(f"Cache hit for models: {paper_title[:50]}...")
            return cached

        logging.debug(f"API call for models: {paper_title[:50]}...")
        try:
            models = list(
                self._hub_call(
                    self.api.list_models,
                    search=paper_title,
                    limit=limit,
                    sort="downloads",
                )
            )
            results = [self._model_to_dict(m) for m in models]
            self.cache.cache_models(cache_key, results, ttl_days=self.cache_ttl_days)
            return results
        except Exception as e:
            logging.error(f"HF API error for models: {e}")
            return []

    def search_papers_by_title(self, paper_title: str, limit: int = 10) -> list[dict]:
        """Search HuggingFace Daily Papers by title using the REST API.

        Uses /api/papers/search to find papers indexed on HF Daily Papers.

        Args:
            paper_title: Academic paper title to search for
            limit: Maximum papers to return (default: 10)

        Returns:
            List of paper metadata dictionaries with fields:
            id, title, authors, summary, published_at
        """
        cache_key = _normalize_cache_key(paper_title, limit)
        cached = self.cache.get_papers(cache_key)
        if cached is not None:
            logging.debug(f"Cache hit for papers: {paper_title[:50]}...")
            return cached

        logging.debug(f"REST API call for papers: {paper_title[:50]}...")
        try:
            papers_data = self._rest_get("papers/search", {"q": paper_title})[:limit]
            results = [self._paper_to_dict(p) for p in papers_data]
            self.cache.cache_papers(cache_key, results, ttl_days=self.cache_ttl_days)
            return results
        except Exception as e:
            logging.error(f"HF API error for papers: {e}")
            return []

    def get_paper_info(self, paper_id: str) -> dict | None:
        """Get paper info including the paper's actual GitHub repo.

        Uses GET /api/papers/{paper_id}; the result includes githubRepo,
        githubStars, ai_keywords, title, authors, summary, etc.

        Args:
            paper_id: Paper ID (arXiv ID like "2307.03172")

        Returns:
            Paper metadata dictionary, or None if not found or on error.
        """
        logging.debug(f"REST API call for paper info: {paper_id}")
        try:
            return self._rest_get(f"papers/{paper_id}")
        except Exception as e:
            logging.warning(f"Failed to fetch paper info for {paper_id}: {e}")
            return None

    def get_paper_linked_resources(self, paper_id: str) -> dict:
        """Get models and datasets that CITE this paper via REST API.

        Note: This returns repos that CITE the paper, not the paper's own repos.
        Use get_paper_info() to get the paper's actual GitHub repository.

        Args:
            paper_id: Paper ID from HF Papers API (e.g., arXiv ID like "2301.12345")

        Returns:
            {"citing_models": [...], "citing_datasets": [...]}
        """
        results = {"citing_models": [], "citing_datasets": []}

        try:
            # GET /api/arxiv/{arxiv_id}/repos -> {"models": [], "datasets": [], ...}
            repos_data = self._rest_get(f"arxiv/{paper_id}/repos")

            for model in repos_data.get("models", []):
                results["citing_models"].append(
                    {
                        "modelId": model.get("id", ""),
                        "author": model.get("author"),
                        "tags": model.get("tags", []),
                        "pipeline_tag": model.get("pipeline_tag"),
                        "downloads": model.get("downloads", 0),
                        "likes": model.get("likes", 0),
                        "card_data": model.get("cardData", {}),
                    }
                )

            for dataset in repos_data.get("datasets", []):
                results["citing_datasets"].append(
                    {
                        "datasetId": dataset.get("id", ""),
                        "author": dataset.get("author"),
                        "tags": dataset.get("tags", []),
                        "downloads": dataset.get("downloads", 0),
                        "likes": dataset.get("likes", 0),
                        "card_data": dataset.get("cardData", {}),
                    }
                )
        except Exception as e:
            logging.warning(f"Failed to fetch linked repos for paper {paper_id}: {e}")

        return results

    def _model_to_dict(self, model_info) -> dict:
        """Convert HfApi ModelInfo object to a JSON-serializable dictionary."""
        return {
            "modelId": model_info.id,
            "author": model_info.author,
            "tags": model_info.tags if model_info.tags else [],
            "pipeline_tag": getattr(model_info, "pipeline_tag", None),
            "downloads": getattr(model_info, "downloads", 0),
            "likes": getattr(model_info, "likes", 0),
            "card_data": _card_data_to_dict(getattr(model_info, "card_data", None)),
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
