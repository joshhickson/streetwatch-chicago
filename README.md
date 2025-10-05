# StreetWatch Chicago: Automated ICE & CBP Activity Mapping

This repository contains the backend service for a real-time geospatial intelligence pipeline designed to map ICE and CBP activity in Chicago based on publicly available social media data. The project is detailed in the [Automated ICE Map Workflow document](10.04.2025%20Automated%20ICE%20Map%20Workflow.md).

## Project Overview

The system is designed as a data pipeline that automates the following processes:
1.  **Ingestion:** Monitors social media (initially Reddit) for relevant posts.
2.  **Processing & Enrichment:** Uses Natural Language Processing (NLP) to extract locations, then geocodes them to get precise coordinates.
3.  **Storage & Formatting:** Stores the processed data in a structured CSV format, ready for visualization.
4.  **Visualization:** The generated CSV can be imported into Google MyMaps to create an interactive map of sightings.

## Current Status: Phase 1 Complete

The initial Python backend, built with Flask, is now complete and has been submitted for review. This version includes the core logic for processing sighting reports.

**Key Features Implemented:**
-   A `/process-sighting` API endpoint that accepts text data.
-   Integration with `spaCy` for Named Entity Recognition (NER) to identify locations.
-   A placeholder for Google Geocoding that simulates coordinate lookups.
-   A robust deduplication strategy to prevent duplicate entries based on time and location proximity.
-   Data storage to a `map_data.csv` file.
-   Secure handling of API keys via environment variables.

## Implementation Roadmap

This project follows the phased implementation plan outlined in the main workflow document.

-   **[✔] Phase 1: Foundational Setup & Configuration:** Project structure created.
-   **[✔] Phase 2: Ingestion Workflow Development (Backend Stub):** The backend endpoint to receive data is complete.
-   **[✔] Phase 3: NLP and API Development:** The core Flask application with spaCy integration is functional.
-   **[✔] Phase 4: End-to-End Integration (Backend Logic):** Data storage and deduplication logic are implemented.
-   **[ ] Phase 5: Visualization, Testing, and Refinement:** This phase requires human intervention.

## Next Steps: Human Intervention Required

To proceed with the full implementation and transition from a simulated backend to a live data pipeline, the following actions are required from the project owner:

1.  **Reddit API Credentials:**
    -   Navigate to your Reddit account's [app preferences](https://www.reddit.com/prefs/apps).
    -   Create a new "script" type application.
    -   Securely provide the **Client ID** and **Client Secret** so they can be configured for the ingestion service.

2.  **Google Geocoding API Key:**
    -   Go to the [Google Cloud Platform Console](https://console.cloud.google.com/).
    -   Create a new project and enable the **Geocoding API**.
    -   Generate a new API key and restrict it to the domain where this application will be hosted.
    -   Set the key as a secret environment variable named `GOOGLE_API_KEY` in this project's environment.

3.  **n8n Workflow Setup:**
    -   Set up an n8n instance (either on n8n Cloud or self-hosted).
    -   Create a workflow that monitors the target subreddits (e.g., r/chicago) for relevant keywords.
    -   Configure the workflow to send an HTTP POST request to this application's `/process-sighting` endpoint with the post data.

Once these steps are completed, development can continue to integrate the live APIs and build out the full data pipeline.