# Changelog

Notable changes to SciLEx are documented here.

## Recent Improvements

### Filtering System
- **ItemType Filtering**: New whitelist mode to focus on specific publication types (journals, conferences, books)
- **Dual Keyword Logic**: Fixed critical bug ensuring papers match keywords from BOTH groups when using dual-group mode
- **Time-Aware Citation Filtering**: Dynamic thresholds based on paper age (grace period for recent papers)
- **Relevance Ranking**: Composite scoring combining keyword frequency, quality, itemType, and citations

### Performance Optimizations
- **Parallel Aggregation**: Multi-core processing for faster deduplication and filtering
- **SQLite Citation Caching**: Persistent cache to avoid redundant API calls
- **Circuit Breaker Pattern**: Fail-fast for broken APIs to save time
- **Bulk Zotero Uploads**: Batch operations for faster exports

### Collection System
- **Idempotent Collections**: Automatic skipping of already completed queries
- **Google Scholar Support**: Added via scholarly Python package
- **ISTEX Support**: French scientific archives integration
- **Progress Tracking**: Real-time progress bars and completion percentages

### Quality and Reliability
- **Enhanced Logging**: Environment-based log control with LOG_LEVEL and LOG_COLOR
- **API Key Validation**: Pre-flight checks before starting collection
- **Better Error Handling**: Specific exception types and proper timeouts
- **Constants Module**: Centralized MISSING_VALUE and validation helpers

### Data Processing
- **Format Converters**: Unified schema converters for all 10 APIs
- **Quality Scoring**: Metadata completeness assessment (0-100 scale)
- **Abstract Quality Validation**: Detects low-quality or placeholder abstracts
- **Deduplication**: DOI, URL, and fuzzy title matching

## Core Features

### Multi-API Collection
- Semantic Scholar (200M+ papers)
- OpenAlex (250M+ works)
- IEEE Xplore (engineering)
- Elsevier (life sciences)
- Springer (multidisciplinary)
- arXiv (preprints)
- HAL (French archive)
- DBLP (CS bibliography)
- Google Scholar (comprehensive)
- ISTEX (French scientific archives)

### Workflow
- Configuration-based keyword search (AND/OR logic)
- Year filtering and field-specific search
- Parallel API collection with rate limiting
- Multi-phase filtering pipeline
- CSV output with unified schema
- Zotero export integration
- PapersWithCode metadata extraction
- Citation network analysis