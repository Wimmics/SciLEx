# SciLEx Web Interface

Complete web-based interface for SciLEx - combining a FastAPI REST backend with a Streamlit frontend for interactive paper collection and analysis.

## Features

### 🎯 Core Functionality

- **Multi-Source Paper Collection**: Search 10+ academic databases simultaneously
  - Free APIs: SemanticScholar, OpenAlex, Arxiv, PubMed, DBLP, HAL
  - Paid APIs: IEEE, Elsevier, Springer
  - Integration: Zotero, HuggingFace

- **Advanced Filtering**: 
  - By year, source, publication type
  - By abstract length and content
  - Relevance ranking by keywords

- **Configuration Management**:
  - Easy API key configuration through web interface
  - Persistent storage of settings
  - Support for multiple API tiers

- **Results Management**:
  - View statistics (papers by year, source, citations)
  - Export in multiple formats (CSV, BibTeX, JSON)
  - Interactive filtering of results
  - Pagination and search

- **Pipeline Tracking**:
  - Background job management
  - Real-time progress updates
  - Job history and status monitoring

## Quick Start

### Installation

Install required dependencies:

```bash
# If not already installed
uv add fastapi uvicorn streamlit pandas pyyaml

# Or use the main requirements.txt
pip install -e .
```

### Running the Interface

#### Option 1: Run Both API and Web Interface (Recommended)

```bash
python scilex/webapi/run_interface.py
```

This will:
- Start FastAPI backend on `http://localhost:8000`
- Start Streamlit on `http://localhost:8501`
- Automatically open the web interface in your browser

#### Option 2: Run Only the API

```bash
python scilex/webapi/run_interface.py --api-only
```

API will be available at `http://localhost:8000`
- Interactive API docs: `http://localhost:8000/docs`

#### Option 3: Run Only the Web Interface

```bash
python scilex/webapi/run_interface.py --web-only
```

#### Option 4: Custom Ports

```bash
python scilex/webapi/run_interface.py \
  --api-port 9000 \
  --web-port 8888 \
  --host 0.0.0.0
```

## Usage Guide

### 1. Configure API Keys

1. Click the **⚙️ Configuration** section in the sidebar
2. Expand **🔑 API Keys**
3. Select an API service
4. Enter credentials:
   - **SemanticScholar**: API key (free tier available)
   - **IEEE**: API key
   - **Elsevier**: API key + optional institutional token
   - **Springer**: API key
   - **Zotero**: API key + User ID
   - **HuggingFace**: Access token

5. Click **✅ Save API Configuration**

### 2. Start a New Collection

1. Go to **🔬 New Collection** tab
2. Fill in parameters:
   - **Collection Name**: Unique identifier
   - **Years**: Select publication years
   - **Keywords**: Enter search terms (one per line)
   - **Data Sources**: Choose APIs to search
   - **Quality Filters**: Set minimum standards

3. Click **🚀 Start Collection Pipeline**

### 3. View and Analyze Results

1. Go to **📊 View Results** tab
2. Select a completed collection
3. View statistics:
   - Papers by year (bar chart)
   - Papers by source (bar chart)
   - Total papers, year range, sources, average citations
4. Browse papers with pagination
5. Click on papers to view full details

### 4. Filter and Export

1. Go to **🔍 Filter & Export** tab
2. Apply filters:
   - Year range
   - Data sources
   - Citation count range
   - Abstract length
3. Click **✅ Apply Filters**
4. Export using:
   - **CSV**: Download filtered results
   - **JSON**: Structured format for processing
   - **BibTeX**: For citation management (if available)

### 5. View Collection History

Go to **📈 Collections History** tab to see all past collections with:
- Number of papers
- File size
- Creation date

## API Reference

The FastAPI backend provides REST endpoints for programmatic access:

### Configuration Endpoints

```http
GET /api-config
```
Get current API configuration (with sensitive data masked)

```http
POST /api-config
Content-Type: application/json

{
  "api_name": "SemanticScholar",
  "api_key": "YOUR_KEY"
}
```
Update API configuration

```http
GET /available-apis
```
List all available APIs with descriptions

### Collection Endpoints

```http
POST /pipelines/start
Content-Type: application/json

{
  "collection_config": {
    "keywords": [["machine learning"], ["application"]],
    "years": [2023, 2024],
    "apis": ["SemanticScholar", "OpenAlex"],
    "collect_name": "ml_apps"
  },
  "api_config": {
    "SemanticScholar": {"api_key": "YOUR_KEY"}
  }
}
```
Start a new collection pipeline

```http
GET /pipelines/{job_id}/status
```
Check status of a running pipeline

```http
GET /pipelines
```
List all pipeline jobs

### Results Endpoints

```http
GET /results/{collect_name}?limit=100&skip=0
```
Get aggregated results with pagination

```http
GET /results/{collect_name}/stats
```
Get statistics about results

```http
POST /export
Content-Type: application/json

{
  "collect_name": "ml_apps",
  "format": "csv"
}
```
Export results (csv, json, bibtex)

```http
GET /collections
```
List all available collections

### Filtering Endpoints

```http
POST /filter/{collect_name}
Content-Type: application/json

{
  "enable_itemtype_filter": true,
  "allowed_item_types": ["journalArticle", "conferencePaper"],
  "max_papers": 500
}
```
Apply filters to results

## Examples

### Python API Client

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# 1. Configure API keys
api_config = {
    "api_name": "SemanticScholar",
    "api_key": "YOUR_API_KEY"
}
requests.post(f"{BASE_URL}/api-config", json=api_config)

# 2. Start collection
pipeline_request = {
    "collection_config": {
        "keywords": [["large language model", "LLM"], ["evaluation"]],
        "years": [2023, 2024],
        "apis": ["SemanticScholar", "OpenAlex"],
        "collect_name": "llm_eval_2024"
    },
    "api_config": {
        "SemanticScholar": {"api_key": "YOUR_KEY"}
    }
}
response = requests.post(f"{BASE_URL}/pipelines/start", json=pipeline_request)
job_id = response.json()["job_id"]

# 3. Monitor progress
import time
while True:
    status = requests.get(f"{BASE_URL}/pipelines/{job_id}/status").json()
    print(f"Progress: {status['progress']}% - {status['message']}")
    if status['status'] in ['completed', 'failed']:
        break
    time.sleep(5)

# 4. Get results
results = requests.get(f"{BASE_URL}/results/llm_eval_2024").json()
print(f"Retrieved {results['total']} papers")

# 5. Export to CSV
export_request = {
    "collect_name": "llm_eval_2024",
    "format": "csv"
}
response = requests.post(f"{BASE_URL}/export", json=export_request)
with open("results.csv", "wb") as f:
    f.write(response.content)
```

### Bash/cURL Examples

```bash
# Get available APIs
curl http://localhost:8000/available-apis

# Check API configuration
curl http://localhost:8000/api-config

# Update API key
curl -X POST http://localhost:8000/api-config \
  -H "Content-Type: application/json" \
  -d '{"api_name":"SemanticScholar","api_key":"YOUR_KEY"}'

# List collections
curl http://localhost:8000/collections

# Get collection statistics
curl http://localhost:8000/results/my_collection/stats
```

## Configuration

### Output Directory

Configure where results are saved:

1. In web interface: Set in **Configuration** sidebar
2. Via API: Pass `output_dir` in collection config
3. Default: `{project_root}/output`

### API Modes

**SemanticScholar Modes:**
- `regular`: Standard search endpoint, 50-100 results per page (default)
- `bulk`: Bulk search endpoint, 1000 results per page (requires approval)

### Quality Filters

All supported filters:
- `enable_text_filter`: Remove low-quality papers
- `min_abstract_words`: Minimum abstract length (default: 50)
- `max_abstract_words`: Maximum abstract length (default: 1000)
- `enable_itemtype_filter`: Whitelist publication types
- `allowed_item_types`: Types to allow (journalArticle, conferencePaper, etc.)
- `apply_relevance_ranking`: Sort by keyword relevance
- `max_papers`: Return top N papers by relevance

## Advanced Usage

### Custom Pipeline Scripts

For programmatic access without the web interface:

```python
import sys
from pathlib import Path

# Setup path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crawlers.collector_collection import CollectCollection

# Configure
main_config = {
    "keywords": [["machine learning"], ["application"]],
    "years": [2023, 2024],
    "apis": ["SemanticScholar", "OpenAlex"],
    "collect_name": "ml_apps"
}

api_config = {
    "SemanticScholar": {"api_key": "YOUR_KEY"}
}

# Run
collector = CollectCollection(main_config, api_config)
collector.create_collects_jobs()
```

See [docs/user-guides/python-scripting.md](../../docs/user-guides/python-scripting.md) for more details.

### Integration with Other Tools

**Export to Zotero:**
```python
from scilex.push_to_zotero import main as zotero_main
zotero_main()  # Requires Zotero API key configured
```

**Export to BibTeX:**
```python
from scilex.export_to_bibtex import main as bibtex_main
bibtex_main()  # Creates .bib file
```

## Troubleshooting

### Common Issues

**Port already in use:**
```bash
python scilex/webapi/run_interface.py --api-port 9000 --web-port 8888
```

**API keys not working:**
1. Verify credentials in web interface **Configuration** tab
2. Check API website for current key format
3. Ensure API is not rate-limited
4. Look for error messages in terminal

**Collection producing no results:**
1. Try simpler keywords
2. Expand year range
3. Add more data sources
4. Check data source availability
5. Verify API keys for paid services

**Streamlit not opening in browser:**
- Manually visit `http://localhost:8501`
- Check firewall settings
- Try different browser

**API documentation not loading:**
- Ensure API is running on correct port
- Visit `http://localhost:8000/docs` (interactive)
- Visit `http://localhost:8000/openapi.json` (raw schema)

## Architecture

```
SciLEx Web Interface
├── Backend (FastAPI)
│   ├── /api-config - API key management
│   ├── /pipelines - Job management
│   ├── /results - Data retrieval
│   └── /export - Output handling
│
├── Frontend (Streamlit)
│   ├── New Collection - Pipeline setup
│   ├── View Results - Data exploration
│   ├── Filter & Export - Result refinement
│   ├── Collections History - Past runs
│   └── Help - Documentation
│
└── Core (Python)
    ├── CollectCollection - Multi-API aggregation
    ├── aggregate_collect - Deduplication & filtering
    └── export functions - Format conversion
```

## File Structure

```
scilex/webapi/
├── __init__.py                  # Package initialization
├── scilex_api.py               # FastAPI backend
├── web_interface.py            # Streamlit frontend
├── run_interface.py            # Launch script
└── README.md                   # This file
```

## Performance Tips

1. **Reduce API calls**: Use fewer APIs, narrow year range
2. **Parallel aggregation**: Increase `--workers` (default: 3)
3. **Skip citations**: Use `--skip-citations` flag
4. **Batch operations**: Combine multiple keywords into one search
5. **Filter early**: Apply filters during collection when possible

## Security Notes

- **API Keys**: Stored in `scilex/api.config.yml` (add to `.gitignore`)
- **Sensitive Data**: Masked in API responses
- **CORS**: Enabled for all origins (configure in production)
- **Input Validation**: All user inputs validated
- **HTTPS**: Use reverse proxy (nginx) in production

## Contributing

Want to improve the web interface?

1. Report bugs in GitHub issues
2. Submit feature requests
3. Create pull requests with improvements
4. Add endpoints as needed

## License

Same as SciLEx main project - See `LICENSE` in project root

## Support

- **Documentation**: See [docs/](../../docs/) directory
- **Issues**: Report on GitHub
- **Questions**: Create GitHub discussion

## Changelog

### v1.0.0
- Initial release with FastAPI backend
- Full Streamlit web interface
- Support for all SciLEx features
- Background job management
- Multi-format export
