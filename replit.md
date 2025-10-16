# StreetWatch Chicago - Geospatial Intelligence Pipeline

## Overview

StreetWatch Chicago is a semi-automated geospatial intelligence pipeline that monitors public social media sources for reports of ICE and CBP activity in Chicago. The system ingests data from web sources (initially Reddit, now Google Custom Search), processes text using Natural Language Processing to extract location information, geocodes these locations to precise coordinates, and outputs structured CSV data for visualization on Google MyMaps.

The architecture follows a four-stage pipeline: Ingestion → Processing & Enrichment → Storage & Formatting → Visualization. The system is designed to be cloud-native and AI-augmented, leveraging serverless platforms and managed services for scalability.

## Recent Changes

### October 16, 2025 - CSV Backup System and Reddit Export Tools

**Branch**: `feature/custom-ner-pipeline-fix`

**Latest Work**:
1. Implemented automatic CSV backup system (`src/backup_csv.py`)
   - Creates timestamped backups before each write operation
   - 30-day retention policy with max 100 backups
   - Rollback capability for data recovery
2. Successfully populated CSV with real ICE/CBP sighting data
   - 10 new entries from Google Custom Search API
   - Total database: 34 sightings
   - All core features verified with live data
3. Fixed `gcp_fetch.py` endpoint URL (port 8080 → 5000)
4. Created Reddit post export tools for Gemini analysis
   - `export_reddit_posts.py`: Python script to export Reddit posts as markdown
   - `REDDIT_EXPORT_INSTRUCTIONS.md`: Comprehensive usage guide
   - `pipeline_description.md`: Complete pipeline documentation for AI analysis
   - Enables identification of location extraction failures

**Critical Discovery**: Reddit API blocks cloud IPs (403 errors), preventing access to full post content and comments. This is why cross-street information is not being extracted - system only receives Google Search snippets (~150 chars) instead of full posts with detailed location data in comments.

**Status**: ✅ System operational; Export tools ready for local execution

### October 15, 2025 - Pipeline Fixes and Model Issues Resolved

**Branch**: `feature/custom-ner-pipeline-fix`

**Completed Work**:
1. Fixed LSP type errors in `src/processing.py` (optional context parameter, .labels access)
2. Added home route (`/`) to Flask API with comprehensive documentation
3. Investigated and documented custom NER model issues
4. Permanently disabled broken custom model - system now uses base `en_core_web_sm` by default
5. Verified all core features: temporal extraction, context-aware geocoding, deduplication

**Known Limitations**:
- Base model sometimes misclassifies specific city names as ORG instead of GPE (e.g., "Evanston")
- Custom CHI_LOCATION model has catastrophic forgetting issue and is disabled
- Training data (`data/training_data.jsonl`) has entity span alignment issues

See `KNOWN_ISSUES.md`, `CURRENT_STATUS_REPORT.md`, and `DETAILED_CHANGE_LOG_2025-10-15.md` for detailed technical analysis.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Pipeline Architecture

The system operates as a scheduled data pipeline orchestrated by GitHub Actions that runs hourly. The workflow follows this sequence:

1. **Automated Ingestion**: GitHub Action triggers the `gcp_fetch.py` script on a schedule
2. **Web Search**: Google Custom Search API queries for relevant posts using keywords ("ICE Chicago", "CBP sighting", etc.)
3. **Data Processing**: For each search result, an HTTP POST request is sent to a Flask API endpoint
4. **NLP Extraction**: Flask app (`src/app.py`) processes the text using spaCy NER models to extract location entities
5. **Geocoding**: Extracted locations are geocoded using Google Geocoding API with geographic context awareness
6. **Deduplication**: Source URL-based deduplication prevents duplicate entries
7. **Storage**: Processed data is appended to a CSV file (`data/map_data.csv`)
8. **Visualization**: Manual import of CSV into Google MyMaps (no API available for automation)

### NLP and Entity Recognition

The system uses a dual-model approach for Named Entity Recognition:

- **Custom Model** (`models/custom_ner_model`): Trained on Chicago-specific location patterns with a custom `CHI_LOCATION` label. Currently has training data alignment issues causing it to fail.
- **Fallback Model** (`en_core_web_sm`): Base spaCy model that successfully extracts GPE (cities, states) and LOC (geographic features) entities. Currently operational.

The custom model training pipeline exists in `src/train_ner.py` with training data at `data/training_data.jsonl`, but suffers from entity span misalignment and catastrophic forgetting of standard labels.

### Temporal Processing

The system implements sophisticated temporal extraction using the `dateparser` library:

- Parses relative time expressions ("yesterday", "2 hours ago", "last Friday")
- Falls back to post creation timestamp when no temporal information is found
- Two-step parsing filters out ambiguous short strings

### Context-Aware Geocoding

Geographic disambiguation is handled through a subreddit-to-location mapping system (`SUBREDDIT_CONTEXT_MAP` in `src/processing.py`):

- Maps subreddit names to geographic contexts (e.g., "chicago" → "Chicago, IL, USA")
- Appends context to geocoding queries to prevent misidentification
- Prevents issues like "Armitage" being geocoded to the UK instead of Chicago

### Data Quality Controls

- **Deduplication**: Source URL tracking prevents duplicate entries
- **Structured Logging**: Timestamped log files in `logs/` directory for monitoring
- **Type Safety**: Uses Python type hints (though some LSP errors exist)
- **Testing**: Pytest suite covering integration tests, geocoding, and NER functionality

### Technology Stack

**Backend Framework**: Flask 2.2.2  
**NLP Engine**: spaCy 3.7.5  
**Date Parsing**: dateparser  
**Distance Calculations**: haversine 2.8.0  
**Reddit Integration**: praw 7.7.1 (legacy, now using Google Custom Search)  
**Testing**: pytest with pytest-mock

### File Organization

- `src/app.py`: Flask REST API with `/health` and `/process-sighting` endpoints
- `src/processing.py`: Core NLP and geocoding logic
- `src/gcp_fetch.py`: Data ingestion from Google Custom Search
- `src/train_ner.py`: Custom NER model training pipeline
- `src/logger.py`: Centralized logging system
- `data/map_data.csv`: Output data storage
- `models/custom_ner_model/`: Custom spaCy NER model (currently broken)

## External Dependencies

### APIs and Services

**Google Geocoding API**: Converts location strings to coordinates  
- API Key: Stored in `GOOGLE_GEOCODE_API_KEY` environment variable
- Rate limits apply to free tier usage

**Google Custom Search API**: Web search for relevant posts  
- API Key: `GOOGLE_API_KEY` environment variable
- Search Engine ID: `CUSTOM_SEARCH_ENGINE_ID` environment variable
- Searches entire web for ICE/CBP sighting reports

**Reddit API** (Legacy): Originally used for ingestion  
- Client ID: `REDDIT_API_ID` (GitHub Secrets)
- Secret: `REDDIT_API_SECRET` (GitHub Secrets)
- Now replaced by Google Custom Search

### Cloud Infrastructure

**GitHub Actions**: Orchestration platform running hourly cron jobs  
- Workflow: `.github/workflows/fetch_data.yml`
- Handles Python environment setup, dependency installation, and script execution

**Git LFS**: Large File Storage for model files  
- Stores spaCy models in `models/` directory
- Requires `git lfs pull` after cloning

**Replit** (Historical): Original hosting platform mentioned in architecture docs  
- System designed to run on cloud platforms
- Currently operates via GitHub Actions

### Python Package Dependencies

Core packages in `requirements.txt`:
- Flask==2.2.2: Web framework
- spacy==3.7.5: NLP and NER
- Werkzeug<3.0.0: WSGI utility library
- requests: HTTP client for API calls
- haversine==2.8.0: Geospatial distance calculations
- praw==7.7.1: Reddit API wrapper
- dateparser: Temporal expression parsing

Development packages in `requirements-dev.txt`:
- pytest: Testing framework
- pytest-mock: Mocking utilities

### Data Storage

**CSV File Storage**: `data/map_data.csv`
- Schema: Latitude, Longitude, Timestamp, Title, Description, VideoURL, SourceURL
- No database system currently implemented
- Future considerations for semantic deduplication may require vector database (FAISS)

### Visualization Platform

**Google MyMaps**: Final visualization layer  
- Manual CSV import required (no API available)
- Represents the "human-in-the-loop" constraint
- Alternative: Google Maps JavaScript API for full automation (future consideration)