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

Create in `scilex/crawlers/collectors.py`:

```python
class YourAPI_collector(API_collector):
    """Collector for YourAPI."""

    def __init__(self, config=None):
        super().__init__()
        self.api_name = "YourAPI"  # Must match config
        self.base_url = "https://api.yourapi.com"
        self.rate_limit = 2.0  # requests/second

        if config:
            self.api_key = config.get('yourapi', {}).get('api_key')

    def query_build(self, keywords, year, fields):
        """Build API query string."""
        # Single group mode
        if not keywords[1]:
            query = " OR ".join(keywords[0])
        # Dual group mode
        else:
            g1 = "(" + " OR ".join(keywords[0]) + ")"
            g2 = "(" + " OR ".join(keywords[1]) + ")"
            query = f"{g1} AND {g2}"

        return f"{query} AND year:{year}"

    def run(self, keywords, nb_res, year, fields):
        """Execute collection with pagination."""
        papers = []
        query = self.query_build(keywords, year, fields)

        page = 1
        while len(papers) < nb_res:
            self._apply_rate_limit()
            response = self._make_request(query, page)

            if not response or not response.get('results'):
                break

            papers.extend(response['results'])
            page += 1

        return papers[:nb_res]

    def _make_request(self, query, page):
        """Make HTTP request with timeout."""
        params = {'query': query, 'page': page}
        if self.api_key:
            params['api_key'] = self.api_key

        response = requests.get(
            f"{self.base_url}/search",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
```

## Format Converter

Add to `scilex/crawlers/aggregate.py`:

```python
from scilex.constants import MISSING_VALUE, is_valid

def YourAPItoZoteroFormat(paper):
    """Convert YourAPI format to Zotero."""

    # Determine item type
    item_type = 'journalArticle'  # Default
    pub_type = paper.get('type', '').lower()
    if 'conference' in pub_type:
        item_type = 'conferencePaper'
    elif 'book' in pub_type:
        item_type = 'book'

    # Format authors
    authors = paper.get('authors', [])
    author_str = ', '.join(authors) if authors else MISSING_VALUE

    return {
        'itemType': item_type,
        'title': paper.get('title', MISSING_VALUE),
        'authors': author_str,
        'abstractNote': paper.get('abstract', MISSING_VALUE),
        'date': str(paper.get('year', MISSING_VALUE)),
        'DOI': paper.get('doi', MISSING_VALUE),
        'url': paper.get('url', MISSING_VALUE),
        'publicationTitle': paper.get('journal', MISSING_VALUE),
        'volume': str(paper.get('volume', MISSING_VALUE)),
        'issue': str(paper.get('issue', MISSING_VALUE)),
        'pages': paper.get('pages', MISSING_VALUE),
        'year': str(paper.get('year', MISSING_VALUE)),
        'citation_count': paper.get('citations', 0),
    }
```

## Registration

In `scilex/crawlers/collector_collection.py`:

```python
api_collectors = {
    'SemanticScholar': SemanticScholar_collector,
    'OpenAlex': OpenAlex_collector,
    # Add your collector
    'YourAPI': YourAPI_collector,
}
```

In `scilex/crawlers/aggregate.py`:

```python
format_converters = {
    'SemanticScholar': SemanticScholarToZoteroFormat,
    'OpenAlex': OpenAlexToZoteroFormat,
    # Add your converter
    'YourAPI': YourAPItoZoteroFormat,
}
```

## Configuration

Add to `scilex/api.config.yml.example`:

```yaml
# YourAPI Configuration
yourapi:
  api_key: "your-key-here"

# Rate limits
rate_limits:
  YourAPI: 2.0  # requests/second
```

Add to `scilex/scilex.config.yml.example`:

```yaml
apis:
  - SemanticScholar
  - OpenAlex
  - YourAPI  # Add here
```

## Testing

Create `scilex/API tests/YourAPITest.py`:

```python
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crawlers.collectors import YourAPI_collector
from crawlers.aggregate import YourAPItoZoteroFormat
import yaml

def test_collector():
    # Load config
    with open('scilex/api.config.yml', 'r') as f:
        config = yaml.safe_load(f)

    # Test collection
    collector = YourAPI_collector(config)
    papers = collector.run([["test"]], 10, 2024, ["title"])

    print(f"Retrieved {len(papers)} papers")

    if papers:
        # Test converter
        zotero_item = YourAPItoZoteroFormat(papers[0])
        print(f"Title: {zotero_item['title']}")

if __name__ == "__main__":
    test_collector()
```

Run: `python "scilex/API tests/YourAPITest.py"`

## Key Points

### Rate Limiting

```python
from time import time, sleep

def _apply_rate_limit(self):
    if not hasattr(self, '_last_request'):
        self._last_request = 0

    elapsed = time() - self._last_request
    interval = 1.0 / self.rate_limit

    if elapsed < interval:
        sleep(interval - elapsed)

    self._last_request = time()
```

### Error Handling

```python
try:
    response = self._make_request(query, page)
except requests.Timeout:
    print(f"Timeout on page {page}")
    break
except requests.HTTPError as e:
    if e.response.status_code == 429:
        print("Rate limited")
        sleep(60)
    else:
        raise
```

### Pagination Strategies

```python
# Offset-based
params = {'offset': page * page_size, 'limit': page_size}

# Page-based
params = {'page': page, 'per_page': page_size}

# Cursor-based
params = {'cursor': next_cursor}
```

## Checklist

Before submitting:

- [ ] Collector inherits from `API_collector`
- [ ] Implements all required methods
- [ ] Handles dual keyword logic correctly
- [ ] Rate limiting implemented
- [ ] Format converter uses `MISSING_VALUE`
- [ ] Registered in both dictionaries
- [ ] Config examples added
- [ ] Test script created
- [ ] Code formatted with `ruff format`

## Common Issues

### Case Sensitivity
Ensure `api_name` matches config exactly.

### Missing Data
Always use `MISSING_VALUE` for missing fields, never leave as `None`.

### Rate Limits
Start conservative, test with small batches first.

## Next Steps

See [Architecture](architecture.md) for system design details.