# StreetWatch Chicago - Data Ingestion Pipeline Description

## Overview

StreetWatch Chicago is a semi-automated geospatial intelligence pipeline that monitors social media for reports of ICE and CBP activity in Chicago. This document describes how raw text from the internet becomes structured location data in a CSV file.

**Purpose:** Enable Google Gemini 2.5 Pro to understand the complete data flow and identify why location extraction is failing.

---

## Pipeline Architecture

### Four-Stage Pipeline

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Ingestion  │ --> │  Processing  │ --> │   Storage    │ --> │ Visualization│
│             │     │& Enrichment  │     │& Formatting  │     │              │
└─────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
    Web APIs         NLP + Geocoding         CSV File          Google MyMaps
```

---

## Stage 1: Data Ingestion

### Current Implementation (October 2025)

**Script:** `src/gcp_fetch.py`  
**Trigger:** GitHub Actions (hourly cron job)  
**Data Source:** Google Custom Search JSON API

### How It Works

1. **GitHub Action runs** on schedule (hourly)
2. **Executes search query:** `"ICE OR CBP OR \"Border Patrol\" sighting in Chicago"`
3. **Retrieves 10 search results** from entire web
4. **Extracts from each result:**
   - Title
   - URL (source link)
   - Text snippet (summary)
5. **Attempts to fetch full Reddit content:**
   - Tries to access Reddit JSON API
   - **FAILS with 403 Forbidden** (cloud IPs blocked)
   - **Falls back to snippet only**

### Key Limitation

**Reddit API Blocking:**
- Cloud/datacenter IPs (AWS, GCP, Azure) are blocked by Reddit
- System only receives Google Search snippet (~150 characters)
- **Full post content and comments are NOT accessible**
- This is why cross-street information is missed

### Historical Context

- Originally used Reddit API directly (PRAW library)
- Switched to Google Custom Search due to Reddit API changes
- Reddit blocking cloud IPs is recent behavior (2024-2025)

---

## Stage 2: Data Processing & Enrichment

### Script: `src/processing.py`

This is where text becomes location data.

### Step 2A: Deduplication

**Method:** Source URL checking

```python
# Read existing CSV
existing_urls = set(row['SourceURL'] for row in csv_data)

# Check if new URL already exists
if source_url in existing_urls:
    skip  # Don't process duplicates
```

**Limitation:** Only prevents exact URL duplicates, not semantic duplicates.

### Step 2B: Named Entity Recognition (NER)

**Model Used:** spaCy `en_core_web_sm` (base English model)  
**Custom Model Status:** Disabled (catastrophic forgetting issue)

**How NER Works:**

1. **Load spaCy model** into memory
2. **Process text:** `nlp(text)` 
3. **Extract entities:**
   - `GPE` (Geo-Political Entities): cities, states, countries
   - `LOC` (Locations): geographic features, regions
   - `ORG` (Organizations): Sometimes misclassified as locations

**What Gets Extracted (Examples):**

From snippet: *"ICE checkpoint at Fullerton and Western in Chicago"*
- ✅ Extracts: `["Chicago"]` (GPE)
- ❌ Misses: `["Fullerton", "Western"]` (not recognized as GPE/LOC)

From snippet: *"Saw them on Milwaukee Ave near the Red Line"*
- ✅ Extracts: `["Milwaukee"]` (GPE)
- ❌ Problem: Geocodes to Milwaukee, WI instead of Milwaukee Ave, Chicago

**Known Issues:**

1. **Neighborhood names** classified as ORG instead of GPE
   - Example: "Evanston" → ORG (incorrect)
   
2. **Street names not recognized** as locations
   - "Fullerton" alone → not extracted
   - "Fullerton and Western" → not extracted
   
3. **Context-dependent disambiguation**
   - "Armitage" → geocodes to UK instead of Chicago
   - "Milwaukee" → geocodes to Wisconsin instead of Milwaukee Ave

4. **Snippet truncation**
   - Location info may be cut off in 150-char snippet
   - Comments contain most specific locations but aren't accessed

### Step 2C: Context Enhancement

**Subreddit Context Mapping:**

```python
SUBREDDIT_CONTEXT_MAP = {
    'chicago': 'Chicago, IL, USA',
    'illinois': 'Illinois, USA',
    # etc.
}
```

**How It Helps:**

Original: `"Fullerton"`  
With context: `"Fullerton, Chicago, IL, USA"`  
Geocodes to: Chicago neighborhood ✅ (not Fullerton, CA)

**Limitation:** Only works when subreddit is known (Reddit URLs). Generic web results lack this context.

### Step 2D: Geocoding

**API:** Google Geocoding API  
**Process:**

1. Take extracted location string (e.g., "Chicago")
2. Append context if available: "Chicago, Chicago, IL, USA"
3. Send to Google Geocoding API
4. Receive coordinates + viewport bounds

**Results:**

| Location String | Geocoded Coordinates | Result |
|-----------------|----------------------|--------|
| "Chicago" | 41.88325, -87.6323879 | ✅ City center |
| "Fullerton, Chicago, IL" | 41.9252, -87.6528 | ✅ Neighborhood |
| "Milwaukee" | 42.214, -87.935 | ❌ Milwaukee, WI |
| "U.S." | 41.88325, -87.6323879 | ⚠️ Falls back to context |

**Why Most Coordinates Are The Same:**

- NLP only extracts "Chicago" or "Illinois" (generic)
- Specific cross-streets NOT extracted from snippets
- Comments with detailed locations NOT accessible
- Result: Everything geocodes to Chicago city center

### Step 2E: Temporal Extraction

**Library:** `dateparser`  
**Process:**

1. Search for temporal expressions in text
2. Parse relative times: "2 hours ago", "yesterday"
3. Parse absolute times: "October 15 at 3pm"
4. Fallback: Use post creation timestamp

**Examples:**

| Text | Parsed Timestamp |
|------|------------------|
| "spotted 2 hours ago" | 2025-10-15T14:35:00Z |
| "yesterday at 3pm" | 2025-10-14T15:00:00Z |
| "on 10/15" | 2025-10-15T00:00:00Z |
| [no time info] | [post creation time] |

---

## Stage 3: Data Storage & Formatting

### CSV Output: `data/map_data.csv`

**Schema:**

| Column | Description | Example |
|--------|-------------|---------|
| Title | "Sighting near [location]" | "Sighting near Chicago" |
| Latitude | Decimal degrees | 41.88325 |
| Longitude | Decimal degrees | -87.6323879 |
| Timestamp | ISO 8601 format | 2025-10-15T12:30:00Z |
| Description | Title + snippet | "ICE checkpoint reported..." |
| SourceURL | Direct link | https://reddit.com/r/chicago/... |
| VideoURL | Media link (if any) | [usually empty] |
| Agency | "ICE", "CBP", or "ICE, CBP" | "ICE" |

### Backup System (NEW - Oct 16, 2025)

**Script:** `src/backup_csv.py`

**Automatic Backups:**
- Created BEFORE each CSV write
- Timestamped: `map_data_backup_20251016_004122.csv`
- Retention: 30 days, max 100 backups
- Enables rollback to any previous version

**Why This Matters:**
- Prevents data loss from pipeline errors
- Allows experimentation without risk
- Audit trail of all changes

---

## Stage 4: Visualization

### Google MyMaps (Manual Step)

**Process:**
1. Delete old map layer
2. Import new CSV file
3. Configure pin icons and colors

**Limitation:** No API available for automation
- Cannot programmatically update map
- "Human-in-the-loop" required
- Manual import takes ~2 minutes

**Alternative:** Google Maps JavaScript API (future)
- Would enable full automation
- Requires custom web application
- Significant development effort

---

## Data Flow Example

### Example 1: Successful Extraction

**Input (Google Search Result):**
```
Title: "ICE checkpoint in Chicago"
Snippet: "Saw ICE checkpoint yesterday in Chicago near the loop"
URL: https://www.reddit.com/r/chicago/comments/abc123/
```

**Processing:**
1. Dedup: URL not in CSV ✅
2. NER extracts: ["Chicago", "loop"]
3. Geocode "Chicago": → 41.88325, -87.6323879
4. Parse time "yesterday": → 2025-10-15T00:00:00Z
5. Write to CSV ✅

**CSV Output:**
```
Sighting near Chicago,41.88325,-87.6323879,2025-10-15T00:00:00Z,"Title: ICE checkpoint in Chicago...",https://reddit.com/...,,ICE
```

### Example 2: Failed Cross-Street Extraction

**Input (Google Search Snippet):**
```
Title: "ICE spotted"
Snippet: "15 hours ago ... Just saw ICE at Fullerton and Western. White vans with..."
URL: https://www.reddit.com/r/chicago/comments/xyz789/
```

**What SHOULD Happen:**
1. Extract: ["Fullerton and Western", "Chicago"]
2. Geocode "Fullerton and Western, Chicago": → 41.925, -87.653
3. Precise intersection location ✅

**What ACTUALLY Happens:**
1. NER extracts: ["Fullerton", "Western"] ← both as ORG (wrong!)
2. Neither recognized as location entity
3. No location extracted
4. Falls back to generic "Chicago"
5. Geocodes to: 41.88325, -87.6323879 ❌

**Why It Fails:**
- Base spaCy model doesn't recognize cross-streets
- "Fullerton and Western" is in snippet, but classified wrong
- Full post content (with better context) is inaccessible
- Comments might have full address → never accessed

### Example 3: Comment Contains Key Info (Missed)

**Reddit Post Structure:**
```
Title: "ICE sighting"
Post: "Just saw ICE activity, be careful"

Comments:
  ├─ User1: "Where exactly?"
  ├──── OP: "Fullerton and Western, by the 7-11"
```

**What Current System Gets (via Google snippet):**
```
Snippet: "Just saw ICE activity, be careful ... 23 comments"
```

**What Current System Misses:**
- ❌ Comments not accessible (Reddit blocks cloud IPs)
- ❌ Specific cross-street "Fullerton and Western"
- ❌ Landmark "by the 7-11"
- Result: Extracts only "Chicago" → city center coordinates

**Impact:**
- 90% of precise location data is in comments
- Current pipeline never sees comments
- This is the PRIMARY cause of clustering at city center

---

## Critical Issues Summary

### Issue 1: Reddit API Blocking (CRITICAL)

**Problem:** Cloud IPs (AWS, GCP, Azure) get 403 Forbidden  
**Impact:** No access to full post content or comments  
**Current Workaround:** Use Google Search snippets only  
**Data Loss:** ~90% of location specificity  

**Evidence:**
```
2025-10-16 00:41:17 - WARNING - Failed to fetch Reddit JSON: 403 Client Error: Blocked
2025-10-16 00:41:17 - WARNING - Falling back to Google Search snippet
```

### Issue 2: Cross-Street Recognition (CRITICAL)

**Problem:** Base spaCy model doesn't extract cross-streets  
**Impact:** Specific intersections not identified  
**Examples:**
- "Fullerton and Western" → NOT extracted
- "Milwaukee Ave and North" → NOT extracted
- "Clark and Diversey" → NOT extracted

**Why Custom Model Failed:**
- Catastrophic forgetting (forgot standard GPE/LOC labels)
- Training data had token alignment issues
- Permanently disabled

### Issue 3: Snippet Truncation (HIGH)

**Problem:** Google snippets limited to ~150 characters  
**Impact:** Location info often cut off  
**Example:**
```
Full text: "ICE checkpoint spotted at Fullerton and Western near the Red Line stop, white vans parked on the corner"
Snippet:   "ICE checkpoint spotted at Fullerton and Western near the..."
```

**What Gets Processed:** Truncated text missing key context

### Issue 4: Generic Location Fallback (MEDIUM)

**Problem:** When NER fails, falls back to "Chicago"  
**Impact:** All failures → same coordinates (41.88325, -87.6323879)  
**Frequency:** ~70% of entries

### Issue 5: Misclassification (MEDIUM)

**Problem:** Neighborhoods classified as ORG instead of GPE  
**Examples:**
- "Evanston" → ORG (should be GPE)
- "Western" → ORG (should be GPE/LOC)
- "Fullerton" → ORG (should be GPE/LOC)

---

## What Gemini Should Analyze

### Task 1: Location Extraction Gaps

For each CSV row with coordinates `41.88325, -87.6323879`:

1. **What location info exists in full Reddit post?**
   - Title mentions?
   - Post body mentions?
   - Comment mentions?
   
2. **What was actually extracted?** (from CSV Title column)

3. **What was missed?**
   - Cross-streets in title?
   - Addresses in post body?
   - Specific locations in comments?

### Task 2: Pattern Identification

Identify HOW people report locations:

- **Cross-street format:** "Fullerton and Western", "Clark & Diversey"
- **Landmark reference:** "near the 7-11", "by the Red Line"
- **Address format:** "1234 N Milwaukee Ave"
- **Neighborhood only:** "in Logan Square"
- **Vague reference:** "downtown", "on the west side"

### Task 3: Data Quality Issues

Identify rows that are:

1. **Not actual sightings:**
   - Policy discussions
   - News articles about ICE
   - General warnings
   
2. **Placeholder/test data:**
   - http://example.com URLs
   - http://test.com URLs
   - "ICE checkpoint in Chicago yesterday" (generic test)

3. **Misidentified:**
   - Posts about weather (actual ice)
   - Posts about Illinois Central Railroad (IC, not ICE)

### Task 4: Source Expansion

Based on Reddit posts, identify:

1. **Mentioned platforms:**
   - Facebook groups?
   - Twitter hashtags?
   - Community websites?
   
2. **Alternative sources:**
   - Local news sites
   - Community alert services
   - Activist organization feeds

---

## Technical Specifications

### APIs Used

| API | Purpose | Rate Limit | Cost |
|-----|---------|------------|------|
| Google Custom Search | Find relevant posts | 100/day (free tier) | Free/Paid |
| Google Geocoding | Location → Coordinates | 40,000/month (free) | Free/Paid |
| Reddit JSON API | Full post content | Blocked from cloud | Free |

### Models & Libraries

| Component | Version | Purpose |
|-----------|---------|---------|
| spaCy | 3.7.5 | NLP/NER |
| en_core_web_sm | 3.7.0 | Base English model |
| dateparser | - | Temporal extraction |
| Flask | 2.2.2 | API endpoint |
| requests | - | HTTP calls |

### File Locations

```
streetwatch-chicago/
├── src/
│   ├── app.py              # Flask API endpoint
│   ├── processing.py       # NER + geocoding logic
│   ├── gcp_fetch.py        # Data ingestion script
│   ├── backup_csv.py       # CSV backup system
│   └── logger.py           # Logging utility
├── data/
│   ├── map_data.csv        # Output CSV
│   └── backups/            # Timestamped backups
├── models/
│   └── custom_ner_model/   # Disabled custom model
└── .github/workflows/
    └── fetch_data.yml      # Hourly automation
```

---

## Future Improvements Needed

### Priority 1: Reddit Access Solution

**Options:**
1. **Residential proxy service** ($75-150/month)
   - Rotate residential IPs
   - Access full Reddit content
   - Enable comment extraction
   
2. **Local scraper** (run from home computer)
   - Use personal residential IP
   - Batch export posts
   - Upload to cloud pipeline

3. **Reddit API partnership** (unlikely)
   - Official API access
   - OAuth authentication
   - No IP blocking

### Priority 2: Cross-Street Recognition

**Options:**
1. **Pattern matching:**
   - Regex: `r'\b[A-Z][a-z]+ and [A-Z][a-z]+\b'`
   - Captures "Fullerton and Western"
   
2. **Custom NER model (fixed):**
   - Retrain with rehearsal examples
   - Prevent catastrophic forgetting
   - Custom CHI_LOCATION label

3. **Hybrid approach:**
   - Pattern matching + NER
   - Validate against Chicago street database
   - Geocode intersection

### Priority 3: Comment Analysis

**Requires:**
- Full Reddit access (see Priority 1)
- NLP on all comments, not just title/post
- Extract locations from conversation threads

### Priority 4: Semantic Deduplication

**Current:** URL-based only  
**Needed:** Detect same event from different sources

**Options:**
- Time + location proximity clustering
- TF-IDF similarity
- Vector embeddings (FAISS)

---

## How to Use This Document with Gemini

### Upload These 3 Files:

1. **`consolidated_reddit_posts.md`**
   - All Reddit posts with full content
   - CSV row numbers for mapping
   
2. **`data/map_data.csv`**
   - Current extraction results
   - Shows what was actually captured
   
3. **`pipeline_description.md`** (this file)
   - How the system works
   - What should be extracted vs what is

### Analysis Prompt Template:

```
I've uploaded 3 files about a geolocation extraction pipeline:

1. consolidated_reddit_posts.md - Full Reddit posts with row numbers
2. map_data.csv - Current extraction results  
3. pipeline_description.md - System architecture

The problem: Most coordinates cluster at Chicago center (41.88325, -87.6323879)
instead of specific cross-streets.

Please analyze:

1. For each CSV row with those coordinates, what specific location 
   information exists in the Reddit post that was missed?

2. What patterns do you see in HOW people report locations? 
   (cross-streets, landmarks, addresses, etc.)

3. Which CSV rows are NOT actual sightings? (policy discussions, 
   test data, misidentified posts)

4. What other data sources are mentioned in posts that should be added?

Create a detailed report with specific row numbers and recommendations.
```

---

## Glossary

**NER (Named Entity Recognition):** AI technique to identify entities (people, places, organizations) in text

**GPE (Geo-Political Entity):** spaCy label for cities, states, countries

**LOC (Location):** spaCy label for geographic features (rivers, mountains, regions)

**Geocoding:** Converting location text to coordinates (lat/lng)

**CORS Proxy:** Service that bypasses browser/cloud restrictions to access APIs

**Deduplication:** Removing duplicate entries based on URL or content similarity

**Catastrophic Forgetting:** When training AI on new data makes it forget old knowledge

**Temporal Extraction:** Identifying time/date information from text

**Snippet:** Short preview text from search results (~150 characters)

---

## Document Version

**Version:** 1.0  
**Date:** October 16, 2025  
**Purpose:** Enable Gemini 2.5 Pro analysis of location extraction failures  
**Author:** StreetWatch Chicago Development Team
