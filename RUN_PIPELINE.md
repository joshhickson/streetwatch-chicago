# StreetWatch Chicago - Pipeline Execution Guide

## Overview

This guide explains how to run the StreetWatch Chicago pipeline on your local machine to process ICE/CBP sighting reports and generate geocoded data for visualization.

## Prerequisites

### Required Software
- **Python 3.8+**: Download from [python.org](https://www.python.org/downloads/)
- **Git**: For cloning the repository (optional if you already have the code)
- **Text editor**: VS Code, Sublime, or any code editor

## Cloning the Repository

### Option 1: Clone Without Git LFS (Recommended)

The repository uses Git LFS for large model files, but these files are **not needed** to run the pipeline. The custom model is disabled, and the system uses the base spaCy model instead.

**Skip LFS files when cloning:**

```bash
# Set environment variable to skip LFS
GIT_LFS_SKIP_SMUDGE=1 git clone <repository-url>
cd streetwatch-chicago
```

**Or if you already cloned and got LFS errors:**

```bash
cd streetwatch-chicago

# Skip LFS checkout
git lfs install --skip-smudge

# Pull without LFS files
git pull
```

### Option 2: Clone with Git LFS (If Available)

If you have Git LFS installed and the LFS server is accessible:

```bash
# Install Git LFS first
git lfs install

# Clone normally
git clone <repository-url>
cd streetwatch-chicago
```

**Note:** The missing LFS files (`models/training_data.spacy`, `models/custom_ner_model/*`) are for a custom NER model that is currently disabled. The pipeline works perfectly without them using the standard spaCy model.

### Required API Keys

You need three API keys stored as environment variables:

1. **Google Geocoding API Key** (`GOOGLE_GEOCODE_API_KEY`)
   - Get from: [Google Cloud Console](https://console.cloud.google.com/)
   - Enable: Geocoding API
   
2. **Google Custom Search API Key** (`GOOGLE_API_KEY`)
   - Get from: [Google Cloud Console](https://console.cloud.google.com/)
   - Enable: Custom Search API
   
3. **Google Custom Search Engine ID** (`CUSTOM_SEARCH_ENGINE_ID`)
   - Create at: [Programmable Search Engine](https://programmablesearchengine.google.com/)
   - Configure to search the entire web

## Setup Instructions

### 1. Install Dependencies

```bash
# Install required Python packages
pip install -r requirements.txt

# Install spaCy language model
python -m spacy download en_core_web_sm
```

### 2. Set Environment Variables

**On Windows (PowerShell):**
```powershell
$env:GOOGLE_GEOCODE_API_KEY="your-geocoding-api-key-here"
$env:GOOGLE_API_KEY="your-custom-search-api-key-here"
$env:CUSTOM_SEARCH_ENGINE_ID="your-search-engine-id-here"
```

**On macOS/Linux (Terminal):**
```bash
export GOOGLE_GEOCODE_API_KEY="your-geocoding-api-key-here"
export GOOGLE_API_KEY="your-custom-search-api-key-here"
export CUSTOM_SEARCH_ENGINE_ID="your-search-engine-id-here"
```

**Alternative: Create a `.env` file** (recommended for persistence)
```bash
# Create .env file in project root
GOOGLE_GEOCODE_API_KEY=your-geocoding-api-key-here
GOOGLE_API_KEY=your-custom-search-api-key-here
CUSTOM_SEARCH_ENGINE_ID=your-search-engine-id-here
```

Then load it before running:
```bash
# On Windows (PowerShell)
Get-Content .env | ForEach-Object { $var = $_.Split('='); [Environment]::SetEnvironmentVariable($var[0], $var[1]) }

# On macOS/Linux
export $(cat .env | xargs)
```

### 3. Verify Setup

Check that environment variables are set:

```bash
# Windows PowerShell
echo $env:GOOGLE_GEOCODE_API_KEY

# macOS/Linux
echo $GOOGLE_GEOCODE_API_KEY
```

## Running the Pipeline

### Method 1: Full Pipeline (Server + Data Fetch)

**Step 1: Start the Flask API Server**

Open a terminal and run:

```bash
python -m src.app
```

You should see:
```
* Running on http://127.0.0.1:5000
* Running on all addresses (0.0.0.0)
```

**Step 2: Run Data Fetching (New Terminal)**

Open a **second terminal** and run:

```bash
python src/gcp_fetch.py
```

This will:
1. Search Google for ICE/CBP sighting reports
2. Send each result to the Flask API for processing
3. Extract locations using NLP and pattern matching
4. Geocode locations to coordinates
5. Save data to `data/map_data.csv`

### Method 2: Server Only (Manual Testing)

**Start the Server:**

```bash
python -m src.app
```

**Test with curl or Postman:**

```bash
# Example POST request
curl -X POST http://localhost:5000/process-sighting \
  -H "Content-Type: application/json" \
  -d '{
    "post_text": "ICE checkpoint at Fullerton and Western",
    "source_url": "https://example.com/test",
    "post_timestamp_utc": 1697500000,
    "agency": "ICE",
    "subreddit": "chicago"
  }'
```

**Health Check:**

```bash
curl http://localhost:5000/health
```

Should return: `{"status": "healthy"}`

### Method 3: Direct Processing Script

**Process a single sighting directly:**

```python
from src.processing import process_sighting_text
from datetime import datetime

result = process_sighting_text(
    post_text="ICE checkpoint at 95th and Halsted",
    source_url="https://test.com/example",
    post_timestamp_utc=int(datetime.now().timestamp()),
    agency="ICE",
    context="chicago"
)

print(f"Processed: {result}")
```

## Output Files

### Primary Output
- **`data/map_data.csv`**: Main output file with geocoded sightings
  - Format: Latitude, Longitude, Timestamp, Title, Description, VideoURL, SourceURL, Agency, Origin, BoundingBox

### Backups
- **`data/backups/`**: Automatic timestamped backups before each write
  - Retention: 30 days, max 100 files
  - Format: `map_data_backup_YYYYMMDD_HHMMSS.csv`

### Logs
- **`logs/`**: Detailed execution logs
  - Format: `run-YYYY-MM-DD_HH-MM-SS.log`
  - Contains: NLP extraction details, geocoding results, errors

## Visualization

### Import to Google MyMaps

1. Go to [Google MyMaps](https://www.google.com/mymaps)
2. Create a new map
3. Click "Import" → Select `data/map_data.csv`
4. Map columns:
   - **Position**: Latitude, Longitude
   - **Title**: Title column
   - **Description**: Description column

## Troubleshooting

### Common Issues

**1. "No module named 'src'"**
```bash
# Make sure you're in the project root directory
cd /path/to/streetwatch-chicago

# Run with -m flag
python -m src.app
```

**2. "spaCy model 'en_core_web_sm' not found"**
```bash
# Download the model
python -m spacy download en_core_web_sm
```

**3. Git LFS errors when cloning**

If you see errors about missing LFS files:
```bash
# Clone without LFS (recommended)
GIT_LFS_SKIP_SMUDGE=1 git clone <repository-url>
```

The missing model files are not needed - the system uses the base spaCy model.

**4. "API key not configured"**
```bash
# Verify environment variables are set
echo $GOOGLE_GEOCODE_API_KEY  # macOS/Linux
echo $env:GOOGLE_GEOCODE_API_KEY  # Windows PowerShell
```

**5. All coordinates are (41.88325, -87.6323879)**

This is the default Chicago center coordinate, which means:
- No specific location was found in the text
- The text snippet from Google Search is too short
- Try running the Reddit export script locally to get full post content

**6. "Failed to geocode location"**

Check:
- Google Geocoding API is enabled in Cloud Console
- API key has correct permissions
- API quota is not exceeded

### Checking Logs

**View latest log:**
```bash
# macOS/Linux
tail -f logs/run-*.log

# Windows PowerShell
Get-Content logs/run-*.log -Tail 50 -Wait
```

**Search logs for errors:**
```bash
# macOS/Linux
grep -i "error" logs/run-*.log

# Windows PowerShell
Select-String -Path "logs/run-*.log" -Pattern "error"
```

## Advanced Usage

### Running as a Scheduled Job

**Windows Task Scheduler:**
1. Create a batch file `run_pipeline.bat`:
```batch
@echo off
cd C:\path\to\streetwatch-chicago
call venv\Scripts\activate
python src/gcp_fetch.py
```

2. Schedule in Task Scheduler to run hourly

**macOS/Linux Cron:**
```bash
# Edit crontab
crontab -e

# Add hourly job (every hour at minute 0)
0 * * * * cd /path/to/streetwatch-chicago && python src/gcp_fetch.py
```

### Custom Search Queries

Edit `src/gcp_fetch.py` to customize search terms:

```python
SEARCH_QUERIES = [
    "ICE checkpoint Chicago",
    "CBP sighting Chicago",
    "border patrol Chicago",
    # Add your custom queries here
]
```

### Backup Management

**List backups:**
```bash
ls -lh data/backups/
```

**Restore from backup:**
```bash
# Copy backup to main file
cp data/backups/map_data_backup_20251016_120000.csv data/map_data.csv
```

**Clean old backups (keeps last 30 days):**
```python
from src.backup_csv import cleanup_old_backups
cleanup_old_backups()
```

## Testing the Cross-Street Extraction

The system now includes enhanced pattern-based extraction that captures cross-streets:

**Test cases that should work:**
- "ICE checkpoint at Fullerton and Western"
- "CBP activity near 95th and Halsted"
- "Checkpoint at Milwaukee Ave and Western Ave"
- "Raid on Martin Luther King Jr Drive and 63rd Street"

**Check extraction in logs:**
```bash
grep "Pattern extraction found" logs/run-*.log
```

Should show: `Pattern extraction found X locations: ['Fullerton and Western', ...]`

## Data Quality Monitoring

**Check coordinate distribution:**
```python
import csv

with open('data/map_data.csv', 'r') as f:
    reader = csv.DictReader(f)
    coords = [(float(row['Latitude']), float(row['Longitude'])) for row in reader]
    
    # Count default coordinates
    default = sum(1 for lat, lon in coords if abs(lat - 41.88325) < 0.01)
    print(f"Default coords: {default}/{len(coords)} ({default/len(coords)*100:.1f}%)")
```

**Expected result:** ~50% default coordinates (due to limited snippet data from Google Search API)

## Support

For issues or questions:
1. Check logs in `logs/` directory
2. Review `KNOWN_ISSUES.md` for documented limitations
3. See `replit.md` for system architecture details
4. Check `REDDIT_EXPORT_INSTRUCTIONS.md` for getting full post content

## Next Steps

After successfully running the pipeline:
1. Import `data/map_data.csv` to Google MyMaps for visualization
2. Schedule automatic runs using cron/Task Scheduler
3. Monitor logs for extraction quality
4. Run Reddit export script locally to improve coordinate specificity
