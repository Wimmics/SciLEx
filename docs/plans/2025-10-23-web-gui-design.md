# SciLEx Web GUI Design Document

**Date:** 2025-10-23
**Status:** Approved Design
**Target Audience:** Mixed skill levels (beginners to power users)

## Executive Summary

This document describes the design for a modern web-based graphical user interface (GUI) for SciLEx that enables users to configure academic paper collections, monitor progress in real-time, and manage results through an intuitive browser-based interface. The GUI maintains backward compatibility with existing YAML configuration files through bidirectional synchronization.

## Requirements & Constraints

### Functional Requirements
- Configure collection parameters (keywords, years, APIs) via GUI forms
- Manage API credentials securely
- Start/stop/monitor collection jobs with real-time progress updates
- View job history and browse collected results
- Push results to Zotero with configuration
- Bidirectional sync with existing YAML configuration files

### Non-Functional Requirements
- Support mixed skill levels (beginners to power users)
- Single job execution at a time (sequential processing)
- Real-time progress updates via WebSocket
- Minimal changes to existing codebase
- Cross-platform support (works in any modern browser)

### Constraints
- Must maintain compatibility with existing YAML configuration files
- Must use existing Python collection scripts
- Must respect API rate limits configured per API
- Background jobs run in same process (threading, not multiprocessing)

## Architectural Overview

### Three-Layer Architecture

```
┌─────────────────────────────────────────┐
│         Frontend (React SPA)            │
│  - Configuration forms                  │
│  - Real-time progress dashboard         │
│  - Job history & results browser        │
│  - Visualizations                       │
└────────────┬────────────────────────────┘
             │ REST API + WebSocket
             ▼
┌─────────────────────────────────────────┐
│       Backend (FastAPI)                 │
│  - Config CRUD endpoints                │
│  - WebSocket for real-time updates      │
│  - Background thread pool               │
│  - YAML parser/writer                   │
│  - File watcher (YAML sync)             │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│          Data Layer                     │
│  - YAML files (source of truth)         │
│  - SQLite (job history & logs)          │
│  - In-memory state (active jobs)        │
└─────────────────────────────────────────┘
```

### Technology Stack

**Backend:**
- FastAPI 0.104+ (async web framework with WebSocket support)
- Pydantic V2 (config validation and serialization)
- SQLAlchemy 2.0 (ORM for SQLite database)
- PyYAML (YAML parsing with safe loading)
- Watchdog (file system monitoring for external edits)
- Python threading (background job execution)

**Frontend:**
- React 18+ with TypeScript (type-safe UI framework)
- Vite (fast development and optimized builds)
- Ant Design or Material-UI (component library)
- React Query / TanStack Query (API state management)
- Recharts (data visualizations)
- Native WebSocket API (real-time updates)

**Database:**
- SQLite (lightweight, file-based, no separate server needed)
- Location: `~/.scilex/gui.db`

### Communication Flow

1. **Configuration Updates:**
   - User edits config → React form → FastAPI REST endpoint → Updates YAML files → Returns success
   - External YAML edit → Watchdog detects → FastAPI notifies via WebSocket → React prompts reload

2. **Job Execution:**
   - User clicks "Start" → FastAPI validates config → Creates job entry in SQLite → Spawns thread → Returns job ID
   - Background thread runs collection → Emits progress events → WebSocket broadcasts → React updates UI
   - Thread completes → Updates SQLite → Sends final status → React shows completion

3. **Results Browsing:**
   - User views history → React requests → FastAPI queries SQLite → Returns paginated results
   - User views papers → React requests → FastAPI reads CSV files → Returns formatted data

## Detailed Component Design

### 1. Configuration Editor

#### Collection Configuration (`scilex.config.yml`)

**Keywords Editor:**
- Two-group keyword interface with visual AND/OR logic indicators
- Dynamic add/remove buttons for each group
- Validation: at least one keyword required in group 1
- Help text explaining single vs. dual group semantics

**Year Selector:**
- Multi-select checkboxes OR range slider (2000-2024)
- Quick presets: "Last 5 years", "Last decade", "All available"
- Validation: at least one year selected

**API Selection:**
- Toggle switches for each supported API
- Status indicators:
  - Green: configured and ready
  - Yellow: optional API key missing (will use lower rate limits)
  - Red: required API key missing
- "Test Connection" button per API

**Fields Selection:**
- Checkboxes for: title, abstract, keywords
- Default: title + abstract

**Advanced Options (Collapsible):**
- Collection name (text input)
- Output directory (directory picker)
- Email address (text input, optional)
- Aggregation options:
  - Enable text filtering (checkbox)
  - Fetch citations automatically (checkbox)

**Form Actions:**
- "Save Configuration" (writes to YAML)
- "Discard Changes" (reloads from YAML)
- "Reset to Defaults" (with confirmation)

#### API Credentials Configuration (`api.config.yml`)

**API Key Management:**
- Secure password input fields for each API
- "Show/Hide" toggle per field
- "Test Connection" button validates credentials
- Status indicators (connected/failed)

**Rate Limit Configuration:**
- Sliders for requests per second per API
- Recommended defaults shown
- Warning if set above safe limits
- Help tooltips with API documentation links

**Zotero Configuration:**
- API key input
- "Connect" button → fetches user ID automatically
- Collection browser (dropdown after connection)
- Option to create new collection vs. use existing

#### Bidirectional YAML Sync

**GUI → YAML:**
- Triggered by "Save Configuration" button
- Validates all fields via Pydantic models
- Writes atomically (temp file → rename) to prevent corruption
- Shows success/error toast notification

**YAML → GUI:**
- Watchdog monitors `scilex.config.yml` and `api.config.yml`
- On external change detection:
  - If GUI has no unsaved changes: reload silently
  - If GUI has unsaved changes: show modal with options:
    - "Keep My Changes" (ignore external edit)
    - "Reload from File" (discard GUI changes)
    - "Show Diff" (display side-by-side comparison)

**Conflict Resolution:**
- Diff view shows line-by-line changes
- User can choose which version to keep
- Option to manually merge (advanced users)

### 2. Job Execution & Progress Tracking

#### Job Lifecycle

**States:**
- `queued` - Job created, waiting to start
- `running` - Actively executing
- `paused` - Paused by user (if implemented)
- `completed` - Successfully finished
- `failed` - Error occurred
- `cancelled` - User cancelled

**Job Submission:**
1. User clicks "Start Collection"
2. FastAPI validates configuration (API keys, keywords, etc.)
3. Creates job entry in SQLite with unique ID
4. Spawns background thread
5. Thread imports and executes existing scripts (`run_collecte.py`, etc.)
6. Returns job ID to frontend immediately

**Background Thread Execution:**
- Thread runs in FastAPI process (not subprocess)
- Calls existing collection scripts with progress callbacks
- Callbacks emit events to WebSocket broadcaster
- Thread catches exceptions and updates job status
- On completion, writes final state to SQLite

#### Progress Broadcasting

**WebSocket Protocol:**
```json
{
  "job_id": "uuid",
  "type": "progress_update",
  "phase": "collection",
  "data": {
    "api": "SemanticScholar",
    "current": 45,
    "total": 100,
    "status": "running",
    "message": "Fetching papers for keyword: machine learning"
  }
}
```

**Event Types:**
- `job_started` - Job execution began
- `progress_update` - Incremental progress (per API, per phase)
- `phase_complete` - Collection/aggregation/citations/zotero phase done
- `log_message` - Log line from collection script
- `job_complete` - Job finished successfully
- `job_failed` - Job encountered error
- `job_cancelled` - User cancelled job

**Progress Granularity:**

**Collection Phase:**
- Overall: X/Y APIs completed
- Per API: papers found, queries completed, rate limit delays
- Keywords: current keyword being processed
- Years: current year being processed

**Aggregation Phase:**
- Papers processed for deduplication
- Duplicates found and removed
- Text filter statistics
- Output file written

**Citations Phase:**
- Papers queried for citations
- Citations found
- References extracted
- Rate limit delays (OpenCitations API)

**Zotero Phase:**
- Papers uploaded
- Success/failure counts
- Collection created/updated

#### Progress Dashboard UI

**Active Job Panel:**
- Job title and ID
- Overall progress bar with percentage
- Phase indicator (Collection → Aggregation → Citations → Zotero)
- Per-API progress bars with individual status
- Real-time statistics cards:
  - Papers found
  - Duplicates removed
  - Citations fetched
  - Time elapsed
  - Estimated time remaining

**Live Log Stream:**
- Last 50 lines scrollable
- Auto-scroll to bottom (toggle)
- Log level filtering (INFO, WARNING, ERROR)
- Search/filter logs
- Download full logs button

**Control Buttons:**
- "Pause" (if feasible - may be complex with threading)
- "Cancel" (graceful shutdown)
- "View Full Logs" (opens modal with complete log)
- "View Configuration" (shows job config)

**State Persistence:**
- Progress snapshots saved to SQLite every 10 seconds
- If server restarts, shows "Last known state" from database
- Warning banner: "Server restarted. Job may still be running."

### 3. Integration with Existing Code

#### Modifying Collection Scripts

**Approach:** Minimal invasive changes with backward compatibility

**Pattern:**
```python
# In run_collecte.py
def run_collection(config, progress_callback=None):
    """
    Run collection with optional progress callback.

    Args:
        config: Collection configuration
        progress_callback: Optional function(event_type, data) for progress
    """
    if progress_callback:
        progress_callback('job_started', {'phase': 'collection'})

    for api in config.apis:
        for keyword in config.keywords:
            # Existing collection logic
            results = collect_from_api(api, keyword)

            if progress_callback:
                progress_callback('progress_update', {
                    'api': api,
                    'keyword': keyword,
                    'papers_found': len(results)
                })

    if progress_callback:
        progress_callback('phase_complete', {'phase': 'collection'})
```

**Changes Required:**
1. `run_collecte.py` - Add progress callback parameter
2. `aggregate_collect.py` - Add progress callback for deduplication steps
3. `citations/get_citations.py` - Add progress callback for citation fetching
4. `push_to_Zotero_collect.py` - Add progress callback for upload progress

**Backward Compatibility:**
- Callbacks are optional parameters (default `None`)
- Existing CLI usage unchanged
- If no callback provided, functions work as before

### 4. Job History & Results Browser

#### Job History Table

**Columns:**
- Timestamp (sortable, searchable)
- Collection name / Keywords summary
- APIs used (badge list)
- Papers found (with link to results)
- Status (colored badge)
- Duration
- Actions (View Details, Rerun, Delete)

**Filters:**
- Date range picker
- Status filter (completed, failed, cancelled)
- API filter (multi-select)
- Keyword search

**Sorting:**
- By timestamp (default: newest first)
- By papers found
- By duration

**Pagination:**
- 20 jobs per page
- Infinite scroll option

#### Results Browser

**Paper Table:**
- Columns: Title, Authors, Year, Venue, APIs, DOI, Citations
- Sortable by any column
- Filterable by year range, venue, API source
- Full-text search across title/abstract/authors

**Quick Actions:**
- Click paper → View detailed modal (abstract, full metadata, citation network link)
- Select multiple → Batch export (CSV, BibTeX, RIS)
- Select multiple → Push to Zotero
- "View Duplicates" button (shows merged papers)

**Export Options:**
- Filtered subset or all papers
- Formats: CSV, JSON, BibTeX, RIS
- Include/exclude fields (customizable)

#### Deduplication Visualization

- Visual indicator for papers found in multiple APIs
- Tooltip showing: "Found in: SemanticScholar, IEEE, OpenAlex"
- "Show Duplicates" view with merge history
- Side-by-side comparison of metadata from different APIs

### 5. Visualizations & Analytics

#### API Coverage Chart
- **Type:** Venn diagram or stacked bar chart
- **Shows:** Paper distribution across APIs
- **Interactions:** Click segment → filter papers by API
- **Metrics:** Unique papers per API, overlap percentages

#### Timeline View
- **Type:** Histogram (papers by publication year)
- **Shows:** Distribution of papers over time
- **Interactions:** Click bar → filter papers by year
- **Options:** Group by year/decade

#### Citation Network Preview
- **Type:** Interactive graph (D3.js or Cytoscape.js)
- **Shows:** Citation relationships between papers
- **Interactions:**
  - Hover node → show paper details
  - Click node → highlight connections
  - Drag to explore
- **Limitations:** Shows subset (top 50-100 papers) for performance

#### Statistics Dashboard

**Cards:**
- Total papers collected
- Duplicates removed (percentage)
- Unique DOIs found
- Average publication year
- Most common venue
- Papers with citations (percentage)
- Coverage by document type (journal/conference/preprint)

**Filters:** Apply to entire dashboard, updates all visualizations

### 6. Error Handling & Validation

#### Pre-Submission Validation

**Configuration Warnings:**
- "No API keys configured" → Block submission
- "Required API keys missing" → Block submission with list
- "Year range very large (may take hours)" → Confirm dialog
- "No keywords specified" → Block submission
- "Output directory not writable" → Block submission

**API Health Checks:**
- Optional "Test Configuration" button before submission
- Validates each selected API (rate limit test)
- Shows which APIs are reachable

#### Runtime Error Handling

**API-Specific Failures:**
- Capture API errors (rate limits, timeouts, auth failures)
- Display in error panel with details:
  - API name
  - Error type (429, 401, 500, etc.)
  - Suggested action ("Check API key", "Retry later")
- Continue collection with other APIs

**Retry Strategies:**
- Automatic retry with exponential backoff for transient failures (503, timeout)
- Manual "Retry Failed APIs" button
- Option to "Continue Without Failed APIs"

**Graceful Degradation:**
- If one API fails, others continue
- If aggregation fails, raw data still saved
- If citations fail, proceed to Zotero without citations
- If Zotero fails, papers still available in results browser

#### Notifications

**Toast Types:**
- Success: "Configuration saved", "Job started successfully"
- Warning: "API key missing for IEEE", "Rate limit approaching"
- Error: "Failed to connect to Zotero", "Collection cancelled"
- Info: "Job completed: 150 papers found"

**Notification Actions:**
- Clickable: opens relevant view (error details, job results)
- Dismissible: manual close or auto-dismiss (5 seconds for success, manual for errors)
- Persistent: errors remain until dismissed

### 7. Additional Features

#### Quick Start Wizard
- **Trigger:** First-time launch (no configs detected)
- **Steps:**
  1. Welcome screen with overview
  2. API key setup (required vs. optional)
  3. Test connections
  4. Configure first collection (guided)
  5. Run test collection (small scope: 1 keyword, 1 year, 1 API)

#### Configuration Templates
- **Preset Scenarios:**
  - "Broad CS Survey" (multiple keywords, all APIs, 10-year range)
  - "Focused ML Papers" (specific keywords, ML-relevant APIs, 5-year range)
  - "Recent Publications Only" (broad keywords, last 2 years)
  - "Citation Network Analysis" (small set, enable citations)

- **Custom Templates:**
  - "Save Current Config as Template" button
  - Template library with import/export
  - Share templates (export as JSON)

#### API Quota Monitoring
- **Dashboard Widget:**
  - API name
  - Requests used today
  - Remaining quota
  - Resets at (timestamp)
  - Progress bar visualization

- **Alerts:**
  - Warning at 80% quota usage
  - Block submission at 100% quota
  - Suggest alternate APIs

#### Future Considerations (Not in V1)
- **Scheduling:** Schedule collections to run at specific times (cron-like)
- **Multi-user Support:** Authentication and per-user configurations
- **Collaboration:** Share collections and results with team members
- **Advanced Filters:** Custom filter expressions for aggregation
- **Plugin System:** User-defined API collectors

## Project Structure

```
src/
├── gui/
│   ├── __init__.py
│   ├── __main__.py                      # Entry point: python -m src.gui
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── main.py                      # FastAPI app initialization
│   │   ├── config.py                    # App configuration (settings)
│   │   ├── database.py                  # SQLAlchemy setup
│   │   ├── dependencies.py              # FastAPI dependencies
│   │   │
│   │   ├── api/                         # REST API endpoints
│   │   │   ├── __init__.py
│   │   │   ├── config.py                # Config CRUD endpoints
│   │   │   ├── jobs.py                  # Job management endpoints
│   │   │   ├── results.py               # Results browsing endpoints
│   │   │   └── health.py                # Health check endpoint
│   │   │
│   │   ├── models/                      # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── job.py                   # Job model
│   │   │   ├── log.py                   # Log entry model
│   │   │   └── progress.py              # Progress snapshot model
│   │   │
│   │   ├── schemas/                     # Pydantic schemas
│   │   │   ├── __init__.py
│   │   │   ├── config.py                # Config schemas (scilex + api)
│   │   │   ├── job.py                   # Job schemas
│   │   │   └── progress.py              # Progress event schemas
│   │   │
│   │   ├── services/                    # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── config_sync.py           # YAML bidirectional sync
│   │   │   ├── job_runner.py            # Background job execution
│   │   │   ├── progress_tracker.py      # Progress tracking
│   │   │   └── file_watcher.py          # Watchdog file monitoring
│   │   │
│   │   └── websocket/                   # WebSocket handlers
│   │       ├── __init__.py
│   │       ├── manager.py               # Connection manager
│   │       └── handlers.py              # Event handlers
│   │
│   └── frontend/
│       ├── package.json
│       ├── tsconfig.json
│       ├── vite.config.ts
│       ├── index.html
│       │
│       ├── public/                      # Static assets
│       │   └── favicon.ico
│       │
│       └── src/
│           ├── main.tsx                 # React entry point
│           ├── App.tsx                  # Root component
│           │
│           ├── components/              # Reusable React components
│           │   ├── ConfigEditor/
│           │   │   ├── KeywordsEditor.tsx
│           │   │   ├── YearSelector.tsx
│           │   │   ├── APISelector.tsx
│           │   │   └── AdvancedOptions.tsx
│           │   ├── Dashboard/
│           │   │   ├── ProgressBar.tsx
│           │   │   ├── StatisticsCard.tsx
│           │   │   ├── LogViewer.tsx
│           │   │   └── JobControls.tsx
│           │   ├── Results/
│           │   │   ├── PaperTable.tsx
│           │   │   ├── PaperModal.tsx
│           │   │   └── ExportDialog.tsx
│           │   └── Common/
│           │       ├── Layout.tsx
│           │       ├── Navbar.tsx
│           │       └── Notifications.tsx
│           │
│           ├── pages/                   # Main views (routes)
│           │   ├── Home.tsx
│           │   ├── ConfigPage.tsx
│           │   ├── DashboardPage.tsx
│           │   ├── HistoryPage.tsx
│           │   └── ResultsPage.tsx
│           │
│           ├── hooks/                   # Custom React hooks
│           │   ├── useWebSocket.ts
│           │   ├── useConfig.ts
│           │   ├── useJobs.ts
│           │   └── useResults.ts
│           │
│           ├── services/                # API clients
│           │   ├── api.ts               # Axios instance
│           │   ├── configService.ts
│           │   ├── jobService.ts
│           │   └── resultsService.ts
│           │
│           ├── types/                   # TypeScript types
│           │   ├── config.ts
│           │   ├── job.ts
│           │   └── progress.ts
│           │
│           └── utils/                   # Utility functions
│               ├── formatting.ts
│               └── validation.ts
│
├── run_collecte.py                      # Modified with callbacks
├── aggregate_collect.py                  # Modified with callbacks
├── citations/get_citations.py           # Modified with callbacks
├── push_to_Zotero_collect.py           # Modified with callbacks
└── [existing files...]
```

## Database Schema

### Jobs Table
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

### Logs Table
```sql
CREATE TABLE logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    level TEXT NOT NULL,               -- INFO/WARNING/ERROR
    api TEXT,                           -- API name or NULL
    message TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
```

### Progress Snapshots Table
```sql
CREATE TABLE progress_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    phase TEXT NOT NULL,                -- collection/aggregation/citations/zotero
    api TEXT,                            -- API name or NULL
    current_count INTEGER,
    total_count INTEGER,
    status TEXT,                         -- running/completed/failed
    metadata TEXT,                       -- JSON with additional data
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
```

## API Endpoints

### Configuration Management

**GET `/api/config/scilex`**
- Returns: Current `scilex.config.yml` as JSON
- Response: `ScilexConfig` schema

**PUT `/api/config/scilex`**
- Body: Updated configuration
- Validates and writes to `scilex.config.yml`
- Response: Success/error

**GET `/api/config/api`**
- Returns: Current `api.config.yml` with API keys masked
- Response: `APIConfig` schema (keys shown as `***`)

**PUT `/api/config/api`**
- Body: Updated API configuration
- Validates and writes to `api.config.yml`
- Response: Success/error

**POST `/api/config/test/{api_name}`**
- Tests connection to specific API
- Response: `{ "success": bool, "message": str }`

### Job Management

**GET `/api/jobs`**
- Query params: `?status=completed&limit=20&offset=0`
- Returns: Paginated list of jobs
- Response: `{ "jobs": [Job], "total": int }`

**GET `/api/jobs/{job_id}`**
- Returns: Detailed job info with logs
- Response: `JobDetail` schema

**POST `/api/jobs/start`**
- Body: Optional override config
- Starts new collection job
- Response: `{ "job_id": str }`

**POST `/api/jobs/{job_id}/cancel`**
- Cancels running job
- Response: Success/error

**DELETE `/api/jobs/{job_id}`**
- Deletes job and associated logs
- Response: Success/error

### Results Management

**GET `/api/results/{job_id}/papers`**
- Query params: `?limit=50&offset=0&sort=year&order=desc`
- Returns: Paginated papers from collection
- Response: `{ "papers": [Paper], "total": int }`

**GET `/api/results/{job_id}/export`**
- Query params: `?format=bibtex&fields=title,authors,year`
- Returns: Exported file (CSV/BibTeX/RIS/JSON)
- Response: File download

**GET `/api/results/{job_id}/statistics`**
- Returns: Statistics and analytics for collection
- Response: `JobStatistics` schema

### Health & Status

**GET `/api/health`**
- Returns: API health status
- Response: `{ "status": "healthy", "version": "1.0.0" }`

**WebSocket `/ws/{job_id}`**
- Bidirectional WebSocket connection
- Receives: Progress updates, log messages, job status changes
- Sends: Control commands (pause, cancel)

## Deployment & Running

### Development Mode

**Backend:**
```bash
cd src/gui/backend
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd src/gui/frontend
npm install
npm run dev  # Runs on localhost:3000, proxies API to localhost:8000
```

### Production Mode

**Build Frontend:**
```bash
cd src/gui/frontend
npm run build  # Creates optimized build in dist/
```

**Run Integrated:**
```bash
python -m src.gui  # FastAPI serves static files from frontend/dist/
```

**Configuration:**
- Port: Default `8000`, configurable via `SCILEX_GUI_PORT` environment variable
- Host: Default `localhost`, configurable via `SCILEX_GUI_HOST`
- Database: `~/.scilex/gui.db`

**Browser:**
- Open `http://localhost:8000`

### Deployment Script

**`src/gui/__main__.py`:**
```python
import uvicorn
from .backend.main import app
import os

if __name__ == "__main__":
    port = int(os.getenv("SCILEX_GUI_PORT", "8000"))
    host = os.getenv("SCILEX_GUI_HOST", "localhost")

    print(f"Starting SciLEx GUI on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
```

## Security Considerations

### API Key Protection
- API keys stored in `api.config.yml` (existing pattern)
- Never exposed via API endpoints (masked as `***`)
- Not included in config snapshots stored in database
- Not sent to frontend WebSocket

### CORS Configuration
- Development: Allow `localhost:3000` (React dev server)
- Production: Only allow same origin
- No wildcard CORS allowed

### Input Validation
- All API inputs validated via Pydantic models
- File paths sanitized to prevent directory traversal
- YAML parsing uses `safe_load` only

### Rate Limiting
- Optional: Rate limit API endpoints to prevent abuse
- Job submission throttled: 1 job per minute per user (future: multi-user)

### WebSocket Security
- Job-specific WebSocket URLs (requires job ID)
- Clients can only connect to jobs they created (future: with auth)
- Connection timeout after 1 hour of inactivity

## Testing Strategy

### Backend Testing
- Unit tests for services (config sync, job runner, progress tracker)
- Integration tests for API endpoints (pytest + FastAPI TestClient)
- WebSocket tests (using WebSocket test client)
- Mock external dependencies (YAML files, database)

### Frontend Testing
- Component tests (React Testing Library)
- Integration tests (Playwright/Cypress for E2E)
- WebSocket mock for real-time updates
- Accessibility tests (axe-core)

### Manual Testing Checklist
- [ ] Configuration editor saves to YAML correctly
- [ ] External YAML edits trigger reload prompt
- [ ] Job starts and broadcasts progress updates
- [ ] Progress dashboard updates in real-time
- [ ] Job can be cancelled gracefully
- [ ] Results browser displays papers correctly
- [ ] Export functionality works for all formats
- [ ] Error handling shows appropriate messages
- [ ] API key validation works
- [ ] Zotero integration connects successfully

## Future Enhancements (Post-V1)

### Scheduling & Automation
- Cron-like job scheduling
- Recurring collections (e.g., weekly)
- Email notifications on completion

### Multi-User Support
- User authentication (OAuth/JWT)
- Per-user configurations and job history
- Shared collections and results

### Advanced Analytics
- Citation network analysis tools
- Topic modeling on abstracts
- Collaboration network visualization
- Journal/conference impact metrics

### Plugin System
- User-defined API collectors
- Custom aggregation filters
- Export format plugins

### Mobile Support
- Responsive design for tablets
- Progressive Web App (PWA)
- Mobile push notifications

### Performance Optimizations
- Pagination for large result sets
- Lazy loading for visualizations
- Database indexing for faster queries
- Background job queue (Celery) for distributed execution

## Success Metrics

### User Experience
- Configuration setup time < 5 minutes (first time)
- Job submission < 30 seconds (including validation)
- Real-time updates latency < 500ms
- Results browsing responsive (< 1s page load)

### Technical
- Zero data loss (all jobs persisted)
- Graceful error handling (no crashes)
- YAML sync reliability (100% accuracy)
- WebSocket connection stability (reconnect on failure)

### Adoption
- Power users can still use CLI (backward compatible)
- Beginners can complete collection without documentation
- Mixed-skill teams can collaborate

## Conclusion

This design provides a modern, user-friendly GUI for SciLEx while maintaining backward compatibility with existing YAML configurations and CLI workflows. The FastAPI + React architecture offers flexibility for future enhancements while keeping initial implementation straightforward. Real-time progress tracking via WebSocket ensures users have visibility into long-running collection jobs, and the bidirectional YAML sync allows power users to continue using their preferred workflows.

The phased implementation approach allows for incremental delivery and validation, with the core functionality (configuration + job execution + progress) deliverable in the first phase, followed by results browsing and visualizations in subsequent phases.
