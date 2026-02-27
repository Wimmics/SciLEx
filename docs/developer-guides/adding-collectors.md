# Adding API Collectors Guide

Guide for adding new academic API collectors to SciLEx.

## Overview

Steps to add a collector:
1. Create collector class
2. Implement required methods
3. Create format converter
4. Register collector
5. Add configuration
6. Test

## Collector Class

Create `scilex/crawlers/collectors/your_api.py`:

```python
from .base import API_collector


class YourAPI_collector(API_collector):
    """Collector for YourAPI."""

    def __init__(self, data_query, data_path, api_key):
        super().__init__(data_query, data_path, api_key)
        self.api_name = "YourAPI"  # Must match config and api_collectors dict exactly
        self.api_url = "https://api.yourapi.com/search"
        self.max_by_page = 100  # Results per page

        # Load rate limit from api.config.yml (must be called after self.api_name is set)
        self.load_rate_limit_from_config()

    def get_configurated_url(self):
        """Build the full API URL with query parameters.

        Returns a URL with a `{}` placeholder for the pagination offset,
        which the base class will format before each page request.
        """
        keywords = self.get_keywords()
        year = self.get_year()

        # Build query string from keywords
        query = " OR ".join(keywords)

        return (
            f"{self.api_url}"
            f"?query={query}"
            f"&year={year}"
            f"&limit={self.max_by_page}"
            f"&offset={{}}"  # Placeholder filled by base class
        )

    def parsePageResults(self, response, page):
        """Parse one page of API results.

        Args:
            response: requests.Response object from the API.
            page: Current page number (1-indexed).

        Returns:
            dict with keys:
                - "total": int — total number of results available
                - "results": list — raw paper dicts for this page
        """
        data = response.json()

        return {
            "total": data.get("totalResults", 0),
            "results": data.get("items", []),
        }
```

### Key Points

- **Constructor**: Always call `super().__init__(data_query, data_path, api_key)` first, then set `self.api_name`, then call `self.load_rate_limit_from_config()`.
- **`get_configurated_url()`**: Builds the full URL. Include `{}` as a placeholder where the pagination offset should go — the base class calls `.format(offset)` before each request.
- **`parsePageResults(response, page)`**: Parse one page. Must return a dict with `"total"` (int) and `"results"` (list). The base class calls this and handles saving, buffering, and pagination.
- **Rate limiting**: Do NOT implement rate limiting manually. Call `self.load_rate_limit_from_config()` in `__init__`. The base class `_rate_limit_wait()` handles it automatically before every request.
- **HTTP calls**: Do NOT call `requests.get()` directly. The base class `api_call_decorator()` wraps every request with circuit breaker, retry logic, and 30-second timeout. It is called by `runCollect()` automatically.
- **Pagination**: The base class `runCollect()` handles pagination for offset-based APIs. Only override `runCollect()` if your API uses a fundamentally different pagination mechanism (e.g., cursor-based with state across requests).

### Custom Pagination (Advanced)

If your API uses cursor-based pagination or another non-offset scheme, override `runCollect()`:

```python
def runCollect(self):
    """Override for cursor-based pagination."""
    cursor = None
    page = 1

    while True:
        url = self.get_configurated_url(cursor)
        response = self.api_call_decorator(url)
        page_data = self.parsePageResults(response, page)

        self.savePageResults(page_data, page)
        self.nb_art_collected += len(page_data["results"])

        cursor = page_data.get("next_cursor")
        if not cursor or not page_data["results"]:
            break
        page += 1

    self._flush_buffer()
    return {"state": 1, "last_page": page, "total_art": self.total_art,
            "coll_art": self.nb_art_collected, "id_collect": self.collectId}
```

## Format Converter

Add to `scilex/crawlers/aggregate.py`:

```python
from scilex.constants import MISSING_VALUE, is_valid

def YourAPItoZoteroFormat(paper):
    """Convert YourAPI format to unified Zotero/SciLEx format."""

    # Determine item type
    item_type = 'journalArticle'  # Default
    pub_type = paper.get('type', '').lower()
    if 'conference' in pub_type:
        item_type = 'conferencePaper'
    elif 'book' in pub_type:
        item_type = 'book'

    # Format authors
    authors = paper.get('authors', [])
    author_str = '; '.join(authors) if authors else MISSING_VALUE

    return {
        'itemType': item_type,
        'title': paper.get('title', MISSING_VALUE),
        'authors': author_str,
        'abstractNote': paper.get('abstract', MISSING_VALUE),
        'date': str(paper.get('year', MISSING_VALUE)),
        'DOI': paper.get('doi', MISSING_VALUE),
        'url': paper.get('url', MISSING_VALUE),
        'pdf_url': MISSING_VALUE,  # Populate if API provides open-access PDFs
        'publicationTitle': paper.get('journal', MISSING_VALUE),
        'volume': str(paper.get('volume', MISSING_VALUE)),
        'issue': str(paper.get('issue', MISSING_VALUE)),
        'pages': paper.get('pages', MISSING_VALUE),
        'year': str(paper.get('year', MISSING_VALUE)),
        'citation_count': paper.get('citations', 0),
        'archive': 'YourAPI',
        'archiveID': paper.get('id', MISSING_VALUE),
    }
```

## Registration

### 1. Import and register in `scilex/crawlers/collector_collection.py`

```python
from scilex.crawlers.collectors.your_api import YourAPI_collector

api_collectors = {
    'SemanticScholar': SemanticScholar_collector,
    'OpenAlex': OpenAlex_collector,
    # ...existing collectors...
    'YourAPI': YourAPI_collector,  # Add here
}
```

### 2. Register format converter in `scilex/crawlers/aggregate.py`

```python
format_converters = {
    'SemanticScholar': SemanticScholarToZoteroFormat,
    'OpenAlex': OpenAlexToZoteroFormat,
    # ...existing converters...
    'YourAPI': YourAPItoZoteroFormat,  # Add here
}
```

## Configuration

Add to `scilex/api.config.yml.example`:

```yaml
YourAPI:
  api_key: "your-key-here"  # Omit if no key required
```

Add to `scilex/scilex.config.yml.example`:

```yaml
apis:
  - SemanticScholar
  - OpenAlex
  - YourAPI  # Add here
```

Rate limits are defined in `scilex/config_defaults.py` under `DEFAULT_RATE_LIMITS`. Add an entry for your API:

```python
DEFAULT_RATE_LIMITS = {
    # ...existing APIs...
    "YourAPI": (2.0, 5.0),  # (without_key req/sec, with_key req/sec)
}
```

## Testing

Create `tests/test_your_api.py` using pytest:

```python
import pytest
from unittest.mock import MagicMock, patch
from scilex.crawlers.collectors.your_api import YourAPI_collector
from scilex.crawlers.aggregate import YourAPItoZoteroFormat
from scilex.constants import MISSING_VALUE


DATA_QUERY = {
    "year": 2024,
    "keyword": ["machine learning"],
    "id_collect": 0,
    "total_art": 0,
    "last_page": 0,
    "coll_art": 0,
    "state": 0,
    "max_articles_per_query": -1,
}


@pytest.fixture
def collector(tmp_path):
    return YourAPI_collector(DATA_QUERY, str(tmp_path), api_key=None)


def test_collector_api_name(collector):
    assert collector.api_name == "YourAPI"


def test_get_configurated_url(collector):
    url = collector.get_configurated_url()
    assert "machine learning" in url
    assert "2024" in url
    assert "{}" in url  # Pagination placeholder must be present


def test_parse_page_results(collector):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "totalResults": 42,
        "items": [{"title": "Test Paper", "doi": "10.1234/test"}],
    }

    result = collector.parsePageResults(mock_response, page=1)

    assert result["total"] == 42
    assert len(result["results"]) == 1


def test_format_converter():
    paper = {
        "title": "Test Paper",
        "authors": ["Alice", "Bob"],
        "year": 2024,
        "doi": "10.1234/test",
    }
    item = YourAPItoZoteroFormat(paper)

    assert item["title"] == "Test Paper"
    assert item["authors"] == "Alice; Bob"
    assert item["year"] == "2024"
    assert item["archive"] == "YourAPI"


def test_format_converter_missing_fields():
    item = YourAPItoZoteroFormat({})
    assert item["title"] == MISSING_VALUE
    assert item["authors"] == MISSING_VALUE
```

Run tests:

```bash
uv run python -m pytest tests/test_your_api.py -v
```

## Checklist

Before submitting:

- [ ] Collector file at `scilex/crawlers/collectors/your_api.py`
- [ ] Inherits from `API_collector` with correct constructor signature
- [ ] `self.api_name` set before `self.load_rate_limit_from_config()`
- [ ] `get_configurated_url()` returns URL with `{}` offset placeholder
- [ ] `parsePageResults()` returns `{"total": int, "results": list}`
- [ ] Format converter uses `MISSING_VALUE` for all missing fields
- [ ] Registered in `api_collectors` dict in `collector_collection.py`
- [ ] Format converter registered in `aggregate.py`
- [ ] Rate limit added to `DEFAULT_RATE_LIMITS` in `config_defaults.py`
- [ ] Config examples added (`api.config.yml.example`, `scilex.config.yml.example`)
- [ ] Tests written in `tests/test_your_api.py` and passing
- [ ] Code formatted with `uvx ruff format .` and linted with `uvx ruff check --fix .`

## Common Issues

### Case Sensitivity
`api_name` must match the key in `api_collectors` and the value in `scilex.config.yml` exactly. A mismatch causes papers to be excluded silently.

### Missing Data
Always use `MISSING_VALUE` from `scilex.constants` for missing fields. Never use `None` or empty string `""` — the quality scoring and deduplication logic depends on `MISSING_VALUE` for correct behavior.

### Rate Limits
Start conservative. Test with `--limit` flags and small keyword sets before full collection runs.

## See Also

- [Architecture](architecture.md) — System design and data flow
- `scilex/crawlers/collectors/semantic_scholar.py` — Canonical reference implementation
- `scilex/crawlers/collectors/base.py` — `API_collector` base class
