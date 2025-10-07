# Intensive System Review - 2025-10-07

This document provides a comprehensive overview of the current state of the automated ICE/CBP mapping pipeline as of October 7, 2025.

## 1. System Overview and Objective

The project's goal is to create a semi-automated pipeline that identifies reports of law enforcement activity (specifically ICE and CBP) from public web sources, processes them to extract geographic locations, and formats them for easy import into a Google MyMap for visualization. The system is designed to be a civic awareness tool.

## 2. Data Pipeline Architecture

The pipeline is orchestrated by a GitHub Action that runs on a schedule. It uses the Google Custom Search API to find relevant articles, then processes the text using a custom-trained Natural Language Processing (NLP) model to identify locations. These locations are geocoded, and the final, deduplicated data is stored in a CSV file.

### Mermaid Diagram

```mermaid
graph TD
    A[GitHub Action Schedule <br> (cron: '0 * * * *')] --> B{Run gcp_fetch.py};
    B --> C{Query Google Custom Search API <br> (Keywords: "ICE Chicago", etc.)};
    C --> D[Search Results <br> (Title, Snippet, URL)];
    D --> E{For each result};
    E --> F[Call process_sighting_text];
    subgraph "src/processing.py"
        F --> G{Deduplicate by SourceURL <br> (Check against map_data.csv)};
        G -- Unique --> H{Extract Locations <br> (spaCy NER Model)};
        G -- Duplicate --> I[Discard];
        H --> J{For each location};
        J --> K{Geocode Location <br> (Google Geocoding API)};
        K --> L[Write to CSV <br> (map_data.csv)];
    end
    L --> M((data/map_data.csv));
```

## 3. Component Breakdown

### 3.1. Automation Engine: GitHub Actions

*   **Workflow File:** `.github/workflows/fetch_data.yml`
*   **Trigger:** The workflow runs on a schedule, once every hour (`cron: '0 * * * *'`). It can also be triggered manually via `workflow_dispatch`.
*   **Execution Steps:**
    1.  **Checkout Code:** It checks out the repository code, ensuring it pulls the large model files tracked by Git LFS (`lfs: true`).
    2.  **Setup Python:** It configures a Python 3.10 environment.
    3.  **Install Dependencies:** It installs all required Python packages from `requirements.txt`.
    4.  **Download Base Model:** It downloads the default `en_core_web_sm` spaCy model, which serves as a fallback.
    5.  **Run Fetch Script:** It executes the main data ingestion script, `src/gcp_fetch.py`.

### 3.2. Data Ingestion: Google Custom Search

*   **Script:** `src/gcp_fetch.py`
*   **API Source:** The pipeline now uses the **Google Custom Search JSON API**. It no longer uses the Reddit API.
*   **Websites Searched:** The Custom Search Engine is configured to search the **entire web**.
*   **Search Keywords:** The script currently searches for the following hardcoded queries:
    *   `"ICE sighting Chicago"`
    *   `"CBP checkpoint Illinois"`
    *   `"ICE raid Chicago"`
    *   `"border patrol Illinois"`
*   **Output:** For each search result, the script extracts the title, URL, and text snippet and passes them to the processing module.

### 3.3. Data Processing and Enrichment

*   **Script:** `src/processing.py`
*   **Duplicate Identification:** The primary deduplication strategy is based on the source URL. Before processing a search result, the script reads the existing `data/map_data.csv` file and checks if the `SourceURL` of the new item is already present. If it is, the item is considered a duplicate and is skipped.
*   **Trained Models (NLP):**
    *   **Custom Model:** The system is designed to use a custom-trained spaCy NER model located at `models/custom_ner_model/model-best`. This model is trained to recognize a specific entity label, `CHI_LOCATION`, for Chicago-specific places.
    *   **Fallback Model:** If the custom model fails to load, the script falls back to using spaCy's default `en_core_web_sm` model. **This is the current operational state**, as the custom model, while present, requires more training data to be effective at extracting specific locations.
*   **Address Lookup (Geocoding):**
    *   After the NLP model extracts a location string (e.g., "Chicago", "South Shore"), the script uses the **Google Geocoding API** to convert this text into latitude and longitude coordinates.

### 3.4. Data Storage

*   **File:** `data/map_data.csv`
*   **Schema:** The final output is a CSV file with the following columns:
    *   `Title`: A descriptive title for the map pin.
    *   `Latitude`: The geocoded latitude.
    *   `Longitude`: The geocoded longitude.
    *   `Timestamp`: The ISO 8601 timestamp of when the source article was *processed*.
    *   `Description`: The title and text snippet from the source.
    *   `SourceURL`: A direct hyperlink to the source article or page.
    *   `VideoURL`: (Currently unused) Intended for direct video links.
    *   `Agency`: The agency associated with the search query (e.g., "ICE, CBP").

## 4. Operational Requirements (Environment Variables)

To run the pipeline, the following environment variables must be set:
*   `GOOGLE_API_KEY`: Your Google Cloud API key.
*   `CUSTOM_SEARCH_ENGINE_ID`: The ID for your Programmable Search Engine.

## 5. Current Limitations and Important Considerations

*   **Model Accuracy:** This is the most critical current limitation. The custom NER model has only been trained on 14 examples and is not yet effective. The system currently relies on the fallback model, which can only identify general locations (like "Chicago" or "Illinois") and not the specific cross-streets or neighborhoods this project was designed to find. **The primary next step for this project is a data science task: annotating hundreds of examples in `data/training_data.jsonl` and retraining the model.**
*   **Manual Visualization:** As designed in the project blueprint, the final step of visualizing the data remains a manual process. The user must download the `map_data.csv` file and import it as a new layer into Google MyMaps.
*   **Timestamp is Processing Time:** Due to limitations of the Google Search API, the `Timestamp` column reflects when an article was found and processed by our script, not its original publication date.