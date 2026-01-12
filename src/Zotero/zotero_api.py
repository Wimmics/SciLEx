"""
Zotero API client for managing collections and items.

This module provides a clean interface to interact with the Zotero API,
handling authentication, collection management, and item creation.
"""

import json
import logging
import random
import string
from typing import Any

import pandas as pd
import requests

from src.constants import MISSING_VALUE, ZoteroConstants, is_valid


class ZoteroAPI:
    """
    Client for interacting with the Zotero API.

    This class encapsulates all Zotero API operations including:
    - Authentication and authorization
    - Collection retrieval and creation
    - Item management
    - Bulk operations with error handling

    Attributes:
        user_id: The Zotero user or group ID
        user_role: Either "user" or "group"
        api_key: The Zotero API key for authentication
        base_endpoint: The API endpoint based on user role
    """

    def __init__(self, user_id: str, user_role: str, api_key: str):
        """
        Initialize the Zotero API client.

        Args:
            user_id: Zotero user or group ID
            user_role: Either "user" or "group"
            api_key: Zotero API key for authentication

        Raises:
            ValueError: If user_role is not "user" or "group"
        """
        if user_role not in ["user", "group"]:
            raise ValueError(
                f"Invalid user_role: {user_role}. Must be 'user' or 'group'"
            )

        self.user_id = user_id
        self.user_role = user_role
        self.api_key = api_key
        self.base_endpoint = (
            f"/groups/{user_id}" if user_role == "group" else f"/users/{user_id}"
        )
        self.headers = {"Zotero-API-Key": self.api_key}

    def _get_write_token(self) -> str:
        """
        Generate a random write token for Zotero API.

        Returns:
            A 32-character random token
        """
        return "".join(
            random.choices(
                string.ascii_uppercase + string.ascii_lowercase,
                k=ZoteroConstants.WRITE_TOKEN_LENGTH,
            )
        )

    def _get(self, path: str, params: dict | None = None) -> requests.Response | None:
        """
        Perform a GET request to the Zotero API.

        Args:
            path: API path (e.g., "/collections")
            params: Optional query parameters

        Returns:
            Response object if successful, None otherwise
        """
        url = f"{ZoteroConstants.API_BASE_URL}{self.base_endpoint}{path}"
        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=30
            )
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            logging.error(f"Timeout while accessing {url}")
        except requests.exceptions.RequestException as e:
            logging.error(f"GET request failed for {url}: {e}")
        return None

    def _post(self, path: str, data: Any) -> requests.Response | None:
        """
        Perform a POST request to the Zotero API.

        Args:
            path: API path (e.g., "/items")
            data: Data to send (will be JSON-encoded)

        Returns:
            Response object if successful, None otherwise
        """
        url = f"{ZoteroConstants.API_BASE_URL}{self.base_endpoint}{path}"
        post_headers = self.headers.copy()
        post_headers.update(
            {
                "Zotero-Write-Token": self._get_write_token(),
                "Content-Type": "application/json",
            }
        )

        try:
            response = requests.post(
                url, headers=post_headers, data=json.dumps(data), timeout=30
            )
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            logging.error(f"Timeout while posting to {url}")
        except requests.exceptions.RequestException as e:
            logging.error(f"POST request failed for {url}: {e}")
        return None

    def get_collections(self, limit: int = 100) -> list[dict] | None:
        """
        Retrieve all collections for the user/group.

        Args:
            limit: Maximum number of collections to retrieve per request

        Returns:
            List of collection dictionaries, or None if request failed
        """
        response = self._get("/collections", params={"limit": limit})
        if response:
            try:
                return response.json()
            except ValueError as e:
                logging.error(f"Failed to parse collections JSON: {e}")
        return None

    def find_collection_by_name(self, name: str) -> dict | None:
        """
        Find a collection by its name.

        Args:
            name: The collection name to search for

        Returns:
            Collection dictionary if found, None otherwise
        """
        collections = self.get_collections()
        if not collections:
            return None

        for collection in collections:
            if collection.get("data", {}).get("name") == name:
                logging.info(f"Found existing collection: '{name}'")
                return collection

        return None

    def create_collection(self, name: str) -> dict | None:
        """
        Create a new collection.

        Args:
            name: Name for the new collection

        Returns:
            Created collection dictionary if successful, None otherwise
        """
        logging.info(f"Creating collection: '{name}'")
        response = self._post("/collections", data=[{"name": name}])

        if response and response.status_code in [200, 201]:
            logging.info(f"Successfully created collection '{name}'")
            # Re-fetch to get the key
            return self.find_collection_by_name(name)
        return None

    def get_or_create_collection(self, name: str) -> dict | None:
        """
        Get an existing collection or create it if it doesn't exist.

        Args:
            name: Collection name to find or create

        Returns:
            Collection dictionary if successful, None otherwise
        """
        # Try to find existing collection
        collection = self.find_collection_by_name(name)
        if collection:
            return collection

        # Create if not found
        return self.create_collection(name)

    def get_collection_items(self, collection_key: str, limit: int = 100) -> list[dict]:
        """
        Get all items in a collection.

        Args:
            collection_key: The collection's key
            limit: Items per page

        Returns:
            List of item dictionaries
        """
        items = []
        start = 0

        while True:
            params = {"limit": limit, "start": start}
            response = self._get("/items", params=params)

            if not response:
                break

            try:
                page_items = response.json()
                if not page_items:
                    break

                # Filter items that belong to the collection
                for item in page_items:
                    if collection_key in item.get("data", {}).get("collections", []):
                        items.append(item)

                # Check if there are more items
                total_results = int(response.headers.get("Total-Results", 0))
                if start + limit >= total_results:
                    break

                start += limit
            except (ValueError, KeyError) as e:
                logging.error(f"Error parsing items response: {e}")
                break

        logging.info(f"Found {len(items)} items in collection")
        return items

    def get_existing_item_urls(self, collection_key: str) -> set:
        """
        Get URLs of all existing items in a collection.

        This is useful for checking duplicates before adding new items.
        Returns a set for O(1) lookup performance.

        Args:
            collection_key: The collection's key

        Returns:
            Set of URLs from existing items
        """
        items = self.get_collection_items(collection_key)
        urls = set()

        for item in items:
            url = item.get("data", {}).get("url")
            if url:
                urls.add(url)

        logging.info(f"Found {len(urls)} existing URLs in collection")
        return urls

    def get_item_template(self, item_type: str) -> dict | None:
        """
        Get the Zotero template for a specific item type.

        Args:
            item_type: The Zotero item type (e.g., "journalArticle")

        Returns:
            Template dictionary if successful, None otherwise
        """
        try:
            response = requests.get(
                f"https://api.zotero.org/items/new?itemType={item_type}", timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch template for {item_type}: {e}")
        return None

    def post_item(self, item_data: dict) -> bool:
        """
        Post a single item to Zotero.

        Args:
            item_data: Item data dictionary (must match Zotero schema)

        Returns:
            True if successful, False otherwise
        """
        response = self._post("/items", data=[item_data])
        if response and response.status_code in [200, 201]:
            logging.info(
                f"Successfully posted item: {item_data.get('title', 'Unknown')}"
            )
            return True

        logging.warning(f"Failed to post item: {item_data.get('title', 'Unknown')}")
        return False

    def post_items_bulk(
        self, items: list[dict], batch_size: int = 50
    ) -> dict[str, int]:
        """
        Post multiple items to Zotero using true bulk API calls.

        Zotero API supports up to 50 items per POST request. This method
        batches items appropriately for optimal performance.

        Args:
            items: List of item data dictionaries
            batch_size: Number of items per batch (max 50 per Zotero API)

        Returns:
            Dictionary with counts: {"success": n, "failed": m}
        """
        results = {"success": 0, "failed": 0}

        # Validate batch size
        if batch_size > 50:
            logging.warning(
                f"Batch size {batch_size} exceeds Zotero API limit of 50. Using 50."
            )
            batch_size = 50

        # Process items in batches
        total_batches = (len(items) + batch_size - 1) // batch_size
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            batch_num = (i // batch_size) + 1

            logging.debug(
                f"Posting batch {batch_num}/{total_batches} ({len(batch)} items)"
            )

            response = self._post("/items", data=batch)

            if response and response.status_code in [200, 201]:
                # All items in batch succeeded
                results["success"] += len(batch)
                logging.debug(f"Batch {batch_num} posted successfully")
            else:
                # Entire batch failed - could implement per-item retry here if needed
                results["failed"] += len(batch)
                logging.warning(
                    f"Batch {batch_num} failed - {len(batch)} items not posted"
                )

        logging.info(
            f"Bulk post complete: {results['success']} succeeded, "
            f"{results['failed']} failed across {total_batches} batches"
        )
        return results


def prepare_zotero_item(
    row: pd.Series,
    collection_key: str,
    templates_cache: dict[str, dict],
) -> dict | None:
    """
    Prepare a Zotero item from a DataFrame row.

    Args:
        row: DataFrame row containing paper metadata (Series or named tuple from itertuples)
        collection_key: Key of the target collection
        templates_cache: Dictionary to cache item templates by type

    Returns:
        Prepared item dictionary, or None if item_type is invalid
    """

    # Helper to get value from either Series or named tuple
    def get_value(row, field: str, default=MISSING_VALUE):
        if hasattr(row, "get"):  # pd.Series
            return row.get(field, default)
        else:  # Named tuple from itertuples
            return getattr(row, field, default)

    item_type = get_value(row, "itemType")

    # Handle bookSection -> journalArticle conversion
    if item_type == "bookSection":
        item_type = "journalArticle"

    # Validate item type
    if not is_valid(item_type):
        return None

    # Get or fetch template
    if item_type not in templates_cache:
        api = ZoteroAPI("", "", "")  # Temporary instance just for template
        template = api.get_item_template(item_type)
        if not template:
            return None
        templates_cache[item_type] = template

    # Copy template and set collection
    item = templates_cache[item_type].copy()
    item["collections"] = [collection_key]

    # Map common fields
    common_fields = [
        "publisher",
        "title",
        "date",
        "DOI",
        "archive",
        "url",
        "rights",
        "pages",
        "journalAbbreviation",
        "conferenceName",
        "volume",
        "issue",
    ]

    for field in common_fields:
        field_value = get_value(row, field)
        if field in item and is_valid(field_value):
            item[field] = str(field_value)

    # Handle abstract
    if "abstractNote" in item:
        abstract = get_value(row, "abstract", "")
        item["abstractNote"] = str(abstract)

    # Handle archive location
    if "archiveLocation" in item:
        archive_id = get_value(row, "archiveID", "")
        item["archiveLocation"] = str(archive_id)

    # Handle authors
    authors_str = get_value(row, "authors")
    if is_valid(authors_str):
        authors = str(authors_str).split(";")
        if item.get("creators") and len(item["creators"]) > 0:
            template_author = item["creators"][0].copy()
            item["creators"] = [
                dict(template_author, firstName=auth.strip()) for auth in authors
            ]

    # Ensure URL is valid (use DOI as fallback)
    if not is_valid(item.get("url")):
        doi = item.get("DOI")
        item["url"] = str(doi) if is_valid(doi) else None

    # Handle HF tags (if present in CSV)
    tags_str = get_value(row, "tags", MISSING_VALUE)
    if is_valid(tags_str) and tags_str != MISSING_VALUE:
        tags_list = [tag.strip() for tag in str(tags_str).split(";")]
        tags_list = [t for t in tags_list if t]  # Remove empty strings
        if tags_list:
            item["tags"] = [{"tag": t} for t in tags_list]

    # Handle GitHub repo (if present in CSV)
    github_repo = get_value(row, "github_repo", MISSING_VALUE)
    if is_valid(github_repo) and github_repo != MISSING_VALUE and "archiveLocation" in item:
        item["archiveLocation"] = str(github_repo)

    return item if item.get("url") else None
