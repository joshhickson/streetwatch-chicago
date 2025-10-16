# Reddit Post Export Instructions

## Overview

This tool exports Reddit posts from your StreetWatch Chicago CSV file and consolidates them into a single markdown file for analysis with Google Gemini 2.5 Pro. This helps identify why location extraction is failing and what data is being missed.

---

## Why This Is Needed

**The Problem:**
- Reddit blocks cloud/datacenter IPs (AWS, GCP, Azure, etc.) with 403 errors
- Your current pipeline only gets search snippets, not full post content
- Cross-street information is in comments, which aren't being captured
- This causes coordinates to cluster at Chicago center (41.88325, -87.6323879)

**The Solution:**
- Run this script on your **local computer** (residential IP)
- Export full Reddit posts with all comments as markdown
- Consolidate into one file with CSV row mapping
- Analyze with Gemini to identify extraction failures

---

## Prerequisites

### Required Python Packages

```bash
pip install requests
```

That's it! The script uses only standard library packages plus `requests`.

### System Requirements

- **Python 3.7+** (any modern Python version)
- **Residential internet connection** (home/coffee shop/library - NOT cloud servers)
- **CSV file** with Reddit URLs (default: `data/map_data.csv`)

---

## Installation

### Step 1: Download the Script

Copy the `export_reddit_posts.py` script to your local computer.

### Step 2: Download Your CSV

Download your `data/map_data.csv` file from the project to your local computer.

### Step 3: Install Dependencies

```bash
pip install requests
```

---

## Usage

### Basic Usage (Recommended)

Run from the same directory as your CSV:

```bash
python export_reddit_posts.py data/map_data.csv
```

This will:
- ✅ Find all Reddit URLs in the CSV
- ✅ Export each as `row_001.md`, `row_002.md`, etc. in `reddit_exports/` folder
- ✅ Create `consolidated_reddit_posts.md` with all posts combined
- ✅ Automatically try multiple CORS proxies if one fails

### Advanced Options

#### Limit Number of Posts (Testing)

```bash
# Export only first 5 posts (for testing)
python export_reddit_posts.py data/map_data.csv --max-posts 5
```

#### Custom Output Directory

```bash
python export_reddit_posts.py data/map_data.csv --output-dir my_exports
```

#### Custom Consolidated Filename

```bash
python export_reddit_posts.py data/map_data.csv --consolidated analysis_for_gemini.md
```

#### Specify Proxy Method

```bash
# Auto (tries multiple, recommended)
python export_reddit_posts.py data/map_data.csv --proxy auto

# Force direct connection (may fail)
python export_reddit_posts.py data/map_data.csv --proxy direct

# Use specific CORS proxy
python export_reddit_posts.py data/map_data.csv --proxy codetabs
python export_reddit_posts.py data/map_data.csv --proxy corslol
```

#### Full Example

```bash
python export_reddit_posts.py data/map_data.csv \
  --output-dir reddit_analysis \
  --consolidated gemini_input.md \
  --proxy auto \
  --max-posts 10
```

---

## Understanding the Output

### Individual Files (`reddit_exports/`)

Each Reddit post is saved as a numbered markdown file:

```
reddit_exports/
├── row_002.md    # Post from CSV row 2
├── row_003.md    # Post from CSV row 3
├── row_013.md    # Post from CSV row 13
└── ...
```

**File Format:**
```markdown
<!-- CSV Row: 2 -->
<!-- Source: https://www.reddit.com/r/chicago/comments/1n8rr08/... -->
<!-- Extracted Location: Sighting near Chicago -->
<!-- Coordinates: 41.88325, -87.6323879 -->

# Post Title

Post content...

## Comments

├─ Comment text ⏤ by *username* (↑ 45/ ↓ 2)
├──── Reply text ⏤ by *other_user* (↑ 12/ ↓ 0)
```

### Consolidated File (`consolidated_reddit_posts.md`)

One large file containing all posts with metadata:

```markdown
# Consolidated Reddit Posts for StreetWatch Chicago

Total posts: 25

---

<!-- CSV Row: 2 -->
<!-- Extracted Location: Sighting near Chicago -->
<!-- Coordinates: 41.88325, -87.6323879 -->

# Post Title
...

---

<!-- CSV Row: 3 -->
...
```

This file is ready to upload to Google Gemini 2.5 Pro.

---

## What Each Proxy Does

### Auto Mode (Recommended)
- Tries multiple proxy services automatically
- Falls back if one fails
- Best success rate

### CodeTabs (`codetabs`)
- Free CORS proxy service
- Generally reliable
- Sometimes rate-limited

### CORS.lol (`corslol`)
- Alternative CORS proxy
- Good fallback option

### Direct (`direct`)
- No proxy, direct connection
- **Will fail from cloud IPs**
- Only works from residential IPs

---

## Troubleshooting

### "All proxies failed"

**Cause:** CORS proxies are temporarily down or rate-limited

**Solutions:**
1. Wait 5-10 minutes and try again
2. Try with `--proxy direct` (only works from home internet)
3. Use `--max-posts 5` to test with fewer posts first

### "HTTP 403" errors

**Cause:** Reddit is blocking the IP address

**Solutions:**
1. ✅ Run from **home internet** (not cloud/VPS)
2. ✅ Use `--proxy auto` to try multiple proxies
3. ❌ Don't run from AWS/GCP/Azure/DigitalOcean

### "Invalid Reddit data structure"

**Cause:** URL is not a valid Reddit post

**Solutions:**
1. Check that URL contains `/comments/` (post URLs only)
2. Verify URL is not deleted or removed
3. Script will skip and continue with other posts

### Slow execution

**Normal behavior:**
- Script adds 2-second delay between requests
- Prevents Reddit rate limiting
- 20 posts ≈ 1-2 minutes

---

## Using Results with Google Gemini

### Step 1: Upload Files to Gemini

Upload these 3 files to Google Gemini 2.5 Pro:

1. **`consolidated_reddit_posts.md`** - All Reddit posts with row numbers
2. **`data/map_data.csv`** - The CSV with extraction results
3. **`pipeline_description.md`** - Pipeline documentation (see below)

### Step 2: Gemini Analysis Prompts

**Prompt 1: Identify Missed Locations**
```
I have uploaded:
1. consolidated_reddit_posts.md (Reddit posts with CSV row numbers)
2. map_data.csv (extraction results)
3. pipeline_description.md (how the system works)

Please analyze why locations are not being extracted correctly. For each CSV row:
- What location information exists in the Reddit post?
- What was actually extracted (from CSV)?
- What was missed or extracted incorrectly?
- Are cross-streets mentioned in comments?

Focus on rows with coordinates 41.88325, -87.6323879 (Chicago center fallback).
```

**Prompt 2: Identify Patterns**
```
Based on the Reddit posts, what patterns do you see in HOW people report 
ICE/CBP sightings? What keywords, phrases, or formats are used for locations?

Examples:
- "Checkpoint at Fullerton and Western"
- "ICE at the 7-11 on Milwaukee Ave"
- "Saw them near the Red Line stop"
```

**Prompt 3: Data Quality**
```
Which CSV rows contain:
1. Placeholder/training data (not real sightings)?
2. Misidentified posts (not actually ICE/CBP sightings)?
3. Policy discussions vs actual sighting reports?

List the row numbers for cleanup.
```

**Prompt 4: Source Recommendations**
```
Based on the Reddit posts, what OTHER websites or platforms should be added 
to the Google Custom Search Engine? Are there specific Facebook groups, 
Twitter hashtags, or community sites mentioned?
```

### Step 3: Iterate

Based on Gemini's analysis:
1. Update NER training data with missed patterns
2. Add new location extraction rules
3. Expand search keywords
4. Add new data sources to Google Custom Search

---

## Output File Locations

After successful run:

```
.
├── reddit_exports/              # Individual markdown files
│   ├── row_002.md
│   ├── row_003.md
│   └── ...
├── consolidated_reddit_posts.md # Combined file for Gemini
├── data/
│   └── map_data.csv            # Your CSV (copy this too)
└── pipeline_description.md      # System documentation (see below)
```

---

## Rate Limiting & Best Practices

### Recommendations

✅ **DO:**
- Run from residential internet (home/cafe/library)
- Use `--proxy auto` for best results
- Start with `--max-posts 5` for testing
- Wait 2+ seconds between requests (built-in)
- Export during off-peak hours

❌ **DON'T:**
- Run from cloud servers (AWS/GCP/Azure)
- Remove the delay between requests
- Export same posts repeatedly (wastes API calls)
- Export more than 50 posts at once (rate limits)

### If You Get Rate Limited

Reddit may temporarily block if you request too much:

1. **Wait 15-30 minutes**
2. **Reduce batch size:** `--max-posts 10`
3. **Use different proxy:** Try `--proxy corslol` instead of `codetabs`
4. **Check your IP:** Make sure you're on residential internet

---

## Example Session

```bash
$ python export_reddit_posts.py data/map_data.csv

Reading CSV file: data/map_data.csv
Output directory: reddit_exports
Proxy mode: auto

Found 34 rows in CSV
Found 25 Reddit URLs

[Row 2] https://www.reddit.com/r/chicago/comments/1n8rr08/...
  Trying CodeTabs... ✅ Success
  ✅ Saved to row_002.md

[Row 3] https://www.reddit.com/r/chicago/comments/1ldxqq9/...
  Trying CodeTabs... ✅ Success
  ✅ Saved to row_003.md

...

Consolidating files into consolidated_reddit_posts.md...
✅ Consolidated 25 files

============================================================
EXPORT SUMMARY
============================================================
✅ Successful: 25
❌ Failed: 0

📄 Individual files: reddit_exports/
📄 Consolidated file: consolidated_reddit_posts.md

Next steps:
1. Review the consolidated file
2. Upload to Google Gemini 2.5 Pro for analysis
3. Use with pipeline_description.md for full context
```

---

## Next Steps After Export

### 1. Review Consolidated File

Open `consolidated_reddit_posts.md` and spot-check:
- Are cross-streets visible in post content?
- Are location mentions in comments (not titles)?
- Any patterns in how people report sightings?

### 2. Upload to Gemini

Go to [Google AI Studio](https://aistudio.google.com/) and:
1. Create new chat with Gemini 2.5 Pro
2. Upload `consolidated_reddit_posts.md`
3. Upload `data/map_data.csv`
4. Upload `pipeline_description.md`
5. Use the analysis prompts above

### 3. Act on Insights

Based on Gemini analysis:
- **Update NER model training data** with missed patterns
- **Add extraction rules** for cross-street formats
- **Expand Google Custom Search** with new sources
- **Clean up CSV** by removing non-sighting rows

---

## FAQ

**Q: Why not run this on Replit/cloud?**  
A: Reddit blocks cloud datacenter IPs. You'll get 403 errors. Must run from residential IP.

**Q: How long does it take?**  
A: ~2 seconds per post. 25 posts ≈ 1-2 minutes total.

**Q: What if some posts fail?**  
A: Script continues and reports failed URLs at end. Usually deleted/removed posts.

**Q: Can I re-export specific rows?**  
A: Yes! Edit the CSV to only include rows you want, or modify the script's filter.

**Q: Is this legal?**  
A: Yes, for research/analysis. Reddit's public JSON API is intended for this use.

**Q: Do I need API keys?**  
A: No! Uses Reddit's public JSON API and free CORS proxies.

---

## Support

If you encounter issues:

1. **Check your internet:** Must be residential IP (home/cafe), not cloud
2. **Try different proxy:** `--proxy corslol` or `--proxy codetabs`
3. **Test with fewer posts:** `--max-posts 3`
4. **Check Reddit URL format:** Must contain `/comments/` for posts

---

## Credits

Based on the RedditToMarkdown tool by [farnots](https://github.com/farnots).  
Adapted for StreetWatch Chicago geospatial intelligence pipeline.
