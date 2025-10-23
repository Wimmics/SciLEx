# SciLEx Web GUI

A modern web-based graphical user interface for SciLEx (Science Literature Exploration) that enables users to configure academic paper collections, monitor progress in real-time, and manage results through an intuitive browser-based interface.

## Features

- **Configuration Editor**: GUI-based configuration for keywords, years, and APIs with validation
- **API Credentials Management**: Secure storage and management of API keys for all supported academic databases
- **Real-Time Progress Monitoring**: WebSocket-based live progress updates with phase tracking and statistics
- **Job History**: Browse past collections with filtering, sorting, and detailed statistics
- **Results Browser**: View, search, filter, and export collected papers in multiple formats (CSV, JSON, BibTeX)
- **Integration with Existing Scripts**: Seamless integration with existing SciLEx collection, aggregation, and citation scripts
- **Cross-Platform**: Works on any modern web browser

## Quick Start

### Backend Setup

1. **Install Dependencies**:
   ```bash
   uv sync  # or: pip install -r requirements.txt
   ```

2. **Start the Backend Server**:
   ```bash
   python -m src.gui
   ```
   The backend will start on `http://localhost:8000`

### Frontend Setup

1. **Install Frontend Dependencies**:
   ```bash
   cd src/gui/frontend
   npm install
   ```

2. **Development Server**:
   ```bash
   npm run dev
   ```
   The frontend will be available at `http://localhost:3000` with automatic API proxy to the backend

### Production Build

1. **Build the Frontend**:
   ```bash
   cd src/gui/frontend
   npm run build
   ```

2. **Run in Production**:
   ```bash
   python -m src.gui  # Serves both API and built frontend on port 8000
   ```

## Usage Workflow

### 1. Initial Setup

Visit the **Home** page to see the setup status. You'll need to:

- **Configure API Credentials** (API Keys page):
  - Enter API keys for IEEE, Elsevier, Springer, SemanticScholar (at least one required API key)
  - Configure rate limits per API (defaults are conservative, adjust based on your tier)
  - Test connections to verify credentials

- **Configure Collection Parameters** (Configuration page):
  - Enter search keywords (supports dual-group AND/OR logic)
  - Select years to search
  - Choose APIs to query
  - Set advanced options (collection name, output directory, etc.)

### 2. Start Collection

Click **"Start Collection"** on the Monitor page:
- Configuration validation checks for missing API keys and keywords
- Job is created and queued in the database
- Collection runs in background thread with real-time progress updates
- Progress tracked through 4 phases: Collection → Aggregation → Citations → Zotero

### 3. Monitor Progress

The Monitor page shows:
- **Overall Progress Bar**: Visual indication of job completion
- **Phase Indicator**: Current phase and completion status of each phase
- **Live Log**: Real-time log streaming from collection process
- **Statistics**: Papers found, duplicates removed, citations fetched
- **Control Buttons**: Cancel job, view results, start new collection

### 4. View Results

The History page shows:
- **Job History Table**: All past collections with status, timing, and statistics
- **Filters**: Filter by status, date range, API sources
- **Actions**: View details, export results, rerun jobs
- **Results Browsing**: Table view of collected papers with search and sorting

### 5. Export Results

Multiple export formats available:
- **CSV**: Standard comma-separated values for spreadsheet applications
- **JSON**: Structured data for programmatic use
- **BibTeX**: Bibliography format for LaTeX documents and reference managers

## Architecture

### Backend

- **Framework**: FastAPI (async Python web framework)
- **Database**: SQLite with SQLAlchemy ORM
- **Jobs**: Threaded background execution with progress callbacks
- **Real-Time**: WebSocket connections for live progress updates
- **Configuration**: YAML file synchronization with validation

### Frontend

- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite (fast development and optimized builds)
- **UI Components**: Ant Design 5
- **State Management**: React Query for API data
- **Real-Time**: Native WebSocket API for progress updates
- **Styling**: CSS with responsive design

### Database Schema

**Jobs Table**: Stores collection job metadata
```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,                -- UUID
    name TEXT NOT NULL,                 -- Collection name
    status TEXT NOT NULL,               -- queued/running/completed/failed/cancelled
    config_snapshot TEXT NOT NULL,      -- JSON snapshot of config used
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    papers_found INTEGER DEFAULT 0,
    duplicates_removed INTEGER DEFAULT 0,
    citations_fetched INTEGER DEFAULT 0,
    error_message TEXT,
    output_directory TEXT
);
```

**Logs Table**: Tracks job execution logs
**Progress Snapshots Table**: Persists progress for crash recovery

## API Endpoints

### Configuration
- `GET /api/config/scilex` - Get collection configuration
- `PUT /api/config/scilex` - Update collection configuration
- `GET /api/config/api` - Get API credentials (masked)
- `PUT /api/config/api` - Update API credentials
- `GET /api/config/exists` - Check which configs exist
- `POST /api/config/test/{api_name}` - Test API connection

### Jobs
- `POST /api/jobs/start` - Start new collection job
- `GET /api/jobs` - List all jobs (paginated, filterable)
- `GET /api/jobs/{job_id}` - Get job details with logs
- `POST /api/jobs/{job_id}/cancel` - Cancel running job
- `DELETE /api/jobs/{job_id}` - Delete job

### Results
- `GET /api/results/{job_id}/papers` - Get papers from collection (paginated, searchable)
- `GET /api/results/{job_id}/export` - Export papers (CSV, JSON, BibTeX)
- `GET /api/results/{job_id}/statistics` - Get collection statistics

### Real-Time
- `WebSocket /ws/{job_id}` - Real-time job progress updates

## Configuration Files

### scilex.config.yml
Main configuration file for collection parameters:
```yaml
keywords:
  - ["machine learning", "deep learning"]  # Group 1: OR logic
  - ["nlp", "natural language"]            # Group 2: OR logic with Group 1
years: [2020, 2021, 2022, 2023, 2024]
apis: ["SemanticScholar", "IEEE", "Elsevier"]
fields: ["title", "abstract"]
collect: true
collect_name: "ml_nlp_survey"
output_dir: "output"
aggregate_txt_filter: true
aggregate_get_citations: false
```

### api.config.yml
Credentials and rate limits:
```yaml
ieee_api_key: "your_key"
elsevier_api_key: "your_key"
springer_api_key: "your_key"
semantic_scholar_api_key: "your_key"

rate_limits:
  SemanticScholar: 1.0
  IEEE: 10.0
  Elsevier: 6.0
  Springer: 1.5
```

## Environment Variables

- `SCILEX_GUI_PORT`: Port for GUI server (default: 8000)
- `SCILEX_GUI_HOST`: Host address (default: 127.0.0.1)

## Security

- API keys are masked when displayed in the UI
- Configuration snapshots don't include sensitive keys
- CORS restricted to development origins or same-origin in production
- YAML safe_load only (no arbitrary code execution)
- File paths sanitized to prevent directory traversal

## Troubleshooting

### Backend won't start
- Check Python version (3.8+ required)
- Verify dependencies: `pip install -r requirements.txt`
- Check port 8000 isn't in use: `lsof -i :8000`

### Frontend build fails
- Clear node_modules: `rm -rf node_modules && npm install`
- Check Node version (16+ recommended)

### WebSocket connection fails
- Verify backend is running on correct port
- Check CORS settings in `src/gui/backend/config.py`
- Browser console should show WebSocket URL being attempted

### Jobs don't progress
- Check backend logs for errors
- Verify API credentials are correct
- Ensure at least one API key is configured
- Check output directory is writable

## Development

### Running Tests

Backend:
```bash
pytest src/gui/backend/tests/
```

Frontend:
```bash
cd src/gui/frontend
npm test
```

### Code Quality

Format and lint:
```bash
uvx ruff format src/gui/backend/
uvx ruff check --fix src/gui/backend/
```

### Database Management

Reset database (caution!):
```bash
rm ~/.scilex/gui.db
python -m src.gui  # Will recreate empty database
```

## Performance Considerations

- Jobs run in separate threads (not multiprocessing) for simplicity
- WebSocket connections timeout after 1 hour of inactivity
- Progress snapshots saved every 10 seconds for recovery
- CSV parsing optimized for streaming large result sets
- Frontend pagination prevents loading entire result set

## Future Enhancements

- Multi-user support with authentication
- Scheduled/recurring collections (cron-like)
- Email notifications on job completion
- Advanced analytics and visualization
- Citation network visualization
- Plugin system for custom APIs
- Mobile app support

## Contributing

To extend the GUI:

1. **New API Endpoints**: Add to `src/gui/backend/api/`
2. **New Components**: Add to `src/gui/frontend/src/components/`
3. **Database Models**: Add to `src/gui/backend/models/`
4. **Business Logic**: Add to `src/gui/backend/services/`

## License

Same as SciLEx project

## Support

For issues or questions:
- Check existing GitHub issues
- Review the design documentation in `docs/plans/`
- Check backend logs: `~/.scilex/gui.db` schema
