import requests
import os
import json
import re
from src.logger import log

# --- Configuration ---
API_KEY = os.getenv("GOOGLE_API_KEY")
CUSTOM_SEARCH_ENGINE_ID = os.getenv("CUSTOM_SEARCH_ENGINE_ID")
PROCESSING_ENDPOINT_URL = "http://localhost:8080/process-sighting"

# The query to search for. This can be refined over time.
SEARCH_QUERY = "ICE OR CBP OR \"Border Patrol\" sighting in Chicago"


def extract_subreddit_from_url(url: str) -> str | None:
    """Extracts the subreddit name from a Reddit URL."""
    if not url:
        return None
    match = re.search(r"reddit\.com/r/([^/]+)", url)
    if match:
        return match.group(1)
    return None


def fetch_and_process_data():
    """
    Fetches data from the Google Custom Search API and sends it to the
    processing endpoint.
    """
    log.info("--- Starting data ingestion from Google Custom Search API ---")

    if not API_KEY or not CUSTOM_SEARCH_ENGINE_ID:
        log.critical("Google API Key or Custom Search Engine ID is not set. Aborting.")
        return

    # --- Make the API call to Google Custom Search ---
    search_url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': API_KEY,
        'cx': CUSTOM_SEARCH_ENGINE_ID,
        'q': SEARCH_QUERY,
        'sort': 'date' # Sort by date to get the most recent results
    }

    try:
        response = requests.get(search_url, params=params, timeout=15)
        response.raise_for_status()
        search_results = response.json()
        items = search_results.get("items", [])
        log.info(f"Retrieved {len(items)} items from the search API.")

    except requests.exceptions.RequestException as e:
        log.error(f"Failed to fetch data from Google Custom Search API: {e}", exc_info=True)
        return

    # --- Process each search result ---
    for item in items:
        try:
            source_url = item.get('link')
            # Prepare the payload for our processing service
            payload = {
                "post_text": f"{item.get('title', '')}\n{item.get('snippet', '')}",
                "source_url": source_url,
                # Use the extracted subreddit as context to help with geocoding
                "context": extract_subreddit_from_url(source_url)
            }

            log.info(f"Sending item to processing endpoint: {payload['source_url']} with context: {payload['context']}")

            # Send the data to our Flask app's endpoint
            proc_response = requests.post(PROCESSING_ENDPOINT_URL, json=payload, timeout=20)
            proc_response.raise_for_status()

            log.info(f"Processing response: {proc_response.json().get('message')}")

        except requests.exceptions.RequestException as e:
            log.error(f"Failed to send data to processing endpoint for URL {item.get('link')}: {e}", exc_info=True)
            continue # Move to the next item
        except Exception as e:
            log.error(f"An unexpected error occurred while processing item {item.get('link')}: {e}", exc_info=True)
            continue


if __name__ == "__main__":
    fetch_and_process_data()
    log.info("--- Data ingestion process finished ---")