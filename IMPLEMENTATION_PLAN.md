# Implementation Plan: High-Fidelity Geospatial Intelligence Pipeline

This document provides a concrete, step-by-step plan for implementing the architectural improvements outlined in the `10.07.2025 Map Data Pipeline Improvement Analysis.md`. The goal is to transform the existing data pipeline from a partially functional prototype into a robust, reliable, and accurate system for geospatial event extraction.

The implementation is broken down into three distinct phases, prioritizing the most critical fixes first and building towards a production-grade architecture.

---

## Phase 1: Stabilize Core Functionality & Data Quality

**Objective:** To fix the most critical bugs in the existing pipeline and ensure the data being generated is fundamentally correct and usable. This phase focuses on data accuracy and bringing the system up to the standard of a reliable proof-of-concept.

### **Step 1.1: Fix Custom NER Model Pipeline**
*   **Task:** The current custom NER model is corrupted and unusable. The training process needs to be made more robust.
*   **Action:**
    1.  Rewrite the `src/train_ner.py` script to use spaCy's programmatic training loop (`nlp.update()`). This is more reliable than using CLI commands via `os.system` and prevents model corruption issues.
    2.  Execute the new training script to generate a clean, valid `CHI_LOCATION` model in the `models/custom_ner_model` directory.
    3.  Modify `src/processing.py` to prioritize loading this custom model, ensuring it can fall back to the generic model only if the custom one is explicitly not found.

### **Step 1.2: Implement Context-Aware Geocoding**
*   **Task:** The geocoder currently fails to disambiguate locations (e.g., "Armitage, UK"). It must be made aware of the geographic context of the data source.
*   **Action:**
    1.  Modify the `gcp_fetch.py` script to pass the subreddit name (e.g., "chicago") as part of the payload to the `/process-sighting` endpoint.
    2.  Update the `process_sighting_text` function in `src/processing.py` to accept this context.
    3.  When calling the Google Geocoding API, append the context (e.g., "Chicago, IL") to the location query to ensure accurate, geographically relevant results.

### **Step 1.3: Improve Temporal Expression Parsing**
*   **Task:** The current system fails to parse relative date expressions like "yesterday" or "last Friday".
*   **Action:**
    1.  Refactor the `extract_event_timestamp` function in `src/processing.py`.
    2.  Implement a more robust two-step parsing logic: first, use `dateparser.search_dates` to find candidate strings, then filter out short/ambiguous results (e.g., "no", "on"), and finally re-parse the best candidate with `dateparser.parse` for accuracy.

### **Step 1.4: Update and Verify with Tests**
*   **Task:** Ensure all fixes are covered by automated tests.
*   **Action:**
    1.  Create a new integration test that confirms the custom `CHI_LOCATION` model is loaded and used correctly.
    2.  Update the geocoding tests to assert that the correct geographic context is passed to the geocoding API.
    3.  Update the temporal extraction tests to remove the `xfail` markers and confirm that relative dates are now parsed correctly.
    4.  Run the entire test suite to ensure all tests pass.

---

## Phase 2: Implement Advanced Data Integrity Features

**Objective:** To move beyond simple data logging and create a curated database of unique events by implementing sophisticated deduplication.

### **Step 2.1: Implement Semantic Deduplication**
*   **Task:** The current system only deduplicates based on source URL. It cannot identify multiple posts describing the same event.
*   **Action:**
    1.  Add `sentence-transformers` and `faiss-cpu` to `requirements.txt`.
    2.  In `src/processing.py`, implement a two-layer deduplication system:
        *   **Layer 1:** The existing check for duplicate source URLs.
        *   **Layer 2 (Semantic):** If the URL is new, generate a vector embedding of the post's text using a Sentence-BERT model.
    3.  Create and manage a FAISS index (`models/faiss_index.bin`) to store the embeddings of all unique events.
    4.  Before processing a new post, query the FAISS index to find if a semantically similar post (with a similarity score above a defined threshold) already exists. If so, discard the new post as a duplicate.
    5.  If the post is unique, process it and add its embedding to the FAISS index.

### **Step 2.2: Add Tests for Semantic Deduplication**
*   **Task:** Verify the deduplication logic works as expected.
*   **Action:**
    1.  Create a new unit test in `src/tests/test_processing.py`.
    2.  This test should mock the SentenceTransformer and FAISS models and assert that:
        *   A new, unique event is processed and added to the index.
        *   A semantically similar but textually different event is correctly identified as a duplicate and rejected.
        *   A semantically different event is correctly processed as a new unique item.

---

## Phase 3: Productionize the Architecture

**Objective:** To replace the fragile CSV file-based storage with a robust, scalable, and queryable database backend, preparing the system for a real application.

### **Step 3.1: Migrate Data Storage to Elasticsearch**
*   **Task:** The `map_data.csv` file is not a scalable or efficient data store for a mapping application.
*   **Action:**
    1.  Add the `elasticsearch-py` library to `requirements.txt`.
    2.  Refactor `src/processing.py` to remove the `write_to_csv` function.
    3.  Implement new functions to connect to an Elasticsearch instance.
    4.  Create an Elasticsearch index mapping that defines the data schema, ensuring the location field is of type `geo_point` to enable efficient spatial queries.
    5.  Modify the `process_sighting_text` function to write new, unique event records as documents to the Elasticsearch index.

### **Step 3.2: Update Application and Tests for Elasticsearch**
*   **Task:** The application and tests need to be updated to work with the new data store.
*   **Action:**
    1.  The deduplication logic in `src/processing.py` should be updated to check for existing `source_url` values in Elasticsearch instead of the CSV file.
    2.  The integration tests in `src/tests/test_integration.py` must be updated to mock an Elasticsearch client or connect to a test instance of Elasticsearch to verify that data is written correctly.
    3.  (Optional) A new API endpoint could be created on the Flask app to query Elasticsearch for events within a given geographic area, which would be used by a future map frontend.