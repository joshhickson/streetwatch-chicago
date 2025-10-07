import os
import requests
from datetime import datetime
from src.processing import process_sighting_text
from src.logger import log

# --- API Configuration ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
CUSTOM_SEARCH_ENGINE_ID = os.getenv("CUSTOM_SEARCH_ENGINE_ID")

# --- Search Configuration ---
KEYWORDS = [
    "ICE sighting Chicago",
    "CBP checkpoint Illinois",
    "ICE raid Chicago",
    "border patrol Illinois"
]
AGENCY_STRING = 'ICE, CBP'

def _get_geo_context_from_query(query):
    """
    Extracts a geographic context string from the search query.
    This is a simple implementation based on keywords.
    """
    query_lower = query.lower()
    if "chicago" in query_lower:
        return "Chicago, IL"
    if "illinois" in query_lower:
        return "Illinois, USA"
    return None # Default case

def fetch_and_process_gcp_data():
    """
    Fetches new search results from a Google Custom Search Engine,
    processes them, and stores any identified sightings.
    """
    log.info("--- Starting Google Cloud Platform data fetch ---")

    if not GOOGLE_API_KEY or not CUSTOM_SEARCH_ENGINE_ID:
        log.critical("CRITICAL: GCP credentials (GOOGLE_API_KEY, CUSTOM_SEARCH_ENGINE_ID) are not set. Halting process.")
        return

    total_new_sightings = 0

    for query in KEYWORDS:
        try:
            log.info(f"Searching Google for query: '{query}'")

            # Construct the API request URL
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                'key': GOOGLE_API_KEY,
                'cx': CUSTOM_SEARCH_ENGINE_ID,
                'q': query,
                'num': 5  # Request the top 5 results for each query
            }

            response = requests.get(url, params=params)
            response.raise_for_status()
            search_results = response.json()

            items = search_results.get('items', [])
            log.info(f"Found {len(items)} results for query '{query}'.")

            for item in items:
                title = item.get('title')
                snippet = item.get('snippet')
                source_url = item.get('link')

                if not all([title, snippet, source_url]):
                    continue

                full_text = f"Title: {title}. Snippet: {snippet}"
                log.info(f"Found potential sighting: {source_url}")

                # Use the current time as the timestamp, as publication dates are not reliable
                # in the search API results.
                post_timestamp_utc = datetime.now().timestamp()

                # Get geo context and pass it to the processing function
                geo_context = _get_geo_context_from_query(query)

                new_sightings_count = process_sighting_text(
                    post_text=full_text,
                    source_url=source_url,
                    post_timestamp_utc=post_timestamp_utc,
                    agency=AGENCY_STRING,
                    context=geo_context
                )

                if new_sightings_count > 0:
                    log.info(f"Successfully processed {new_sightings_count} new sightings from source: {source_url}")
                    total_new_sightings += new_sightings_count

        except requests.exceptions.RequestException as e:
            log.error(f"An error occurred while processing query '{query}': {e}", exc_info=True)
        except Exception as e:
            log.error(f"An unexpected error occurred: {e}", exc_info=True)

    log.info(f"--- Finished GCP data fetch. Total new sightings found: {total_new_sightings} ---")

if __name__ == '__main__':
    fetch_and_process_gcp_data()