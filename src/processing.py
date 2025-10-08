import spacy
import requests
import csv
import os
import json
import string
from datetime import datetime
from dateparser import search as dateparser_search
from src.logger import log # Import our new centralized logger

# --- Helper Functions ---

def normalize_text(text: str) -> str:
    """
    Converts text to lowercase and removes common punctuation.
    """
    if not isinstance(text, str):
        return ""
    text = text.lower()
    # Create a translation table to remove punctuation
    translator = str.maketrans('', '', string.punctuation)
    return text.translate(translator)

# --- Model and API Configuration ---

# Define model paths
CUSTOM_MODEL_PATH = 'models/custom_ner_model/model-best'

# Load the spaCy model, preferring the custom model if it exists.
nlp = None
if os.path.exists(CUSTOM_MODEL_PATH):
    try:
        nlp = spacy.load(CUSTOM_MODEL_PATH)
        log.info(f"Custom spaCy model loaded successfully from {CUSTOM_MODEL_PATH}.")
    except Exception as e:
        log.error(f"Error loading custom spaCy model from {CUSTOM_MODEL_PATH}: {e}", exc_info=True)

if nlp is None:
    log.warning("Custom model not found or failed to load. Falling back to default 'en_core_web_sm' model.")
    try:
        nlp = spacy.load("en_core_web_sm")
        log.info("Default spaCy model 'en_core_web_sm' loaded successfully.")
    except Exception as e:
        log.critical(f"Failed to load even the default spaCy model. NLP processing will be disabled. Error: {e}", exc_info=True)
        # nlp remains None

# Constants
GOOGLE_API_KEY = os.getenv("GOOGLE_GEOCODE_API_KEY")
if not GOOGLE_API_KEY:
    log.critical("CRITICAL: GOOGLE_GEOCODE_API_KEY environment variable not set.")

# Use an environment variable for the output file path to allow for test isolation.
# Default to the production file path if the variable is not set.
DATA_FILE = os.getenv('CSV_OUTPUT_FILE', 'data/map_data.csv')

def geocode_location(location_text, context=None):
    """
    Converts a location string to geographic coordinates.
    In integration test mode, it returns a fixed dummy response.
    Otherwise, it calls the Google Geocoding API.
    """
    # If in integration testing mode, return a predictable, dummy response.
    if os.getenv('INTEGRATION_TESTING') == 'true':
        log.info(
            f"INTEGRATION_TESTING mode: Returning mock geocode for "
            f"location='{location_text}' with context='{context}'"
        )
        # This response mimics a successful, approximate geocoding result
        return {
            "lat": 40.6331249, "lng": -89.3985283,
            "bounding_box": {
                "northeast": {"lat": 42.508338, "lng": -87.524529},
                "southwest": {"lat": 36.970298, "lng": -91.513079},
            }
        }

    # Construct the full address string with context if available
    full_address = f"{location_text}, {context}" if context and context.strip() else location_text
    log.info(f"Geocoding location: '{full_address}'")

    if not GOOGLE_API_KEY:
        log.error("Google API key not configured. Cannot geocode.")
        return None

    params = {
        'address': full_address,
        'key': GOOGLE_API_KEY,
    }
    try:
        response = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params=params)
        response.raise_for_status()
        results = response.json().get('results')
        if results:
            result = results[0]
            geometry = result.get('geometry', {})
            location = geometry.get('location', {})

            lat = location.get('lat')
            lng = location.get('lng')

            if not lat or not lng:
                log.warning(f"Geocoding result for '{full_address}' missing lat/lng.")
                return None

            # Prepare the core return data
            geocoded_data = {"lat": lat, "lng": lng, "bounding_box": None}
            log.info(f"Geocoded '{full_address}' to {location}")

            # Check if the result is approximate and extract the bounding box if so
            location_type = geometry.get('location_type')
            if location_type == 'APPROXIMATE':
                viewport = geometry.get('viewport')
                if viewport:
                    geocoded_data['bounding_box'] = viewport
                    log.info(f"Extracted approximate bounding box for '{full_address}': {viewport}")

            return geocoded_data
        else:
            log.warning(f"No geocoding results found for '{full_address}'")
            return None
    except requests.exceptions.RequestException as e:
        log.error(f"Failed to geocode '{full_address}'. Error: {e}", exc_info=True)
        return None

def extract_event_timestamp(text, base_time):
    """
    Extracts a timestamp from text using dateparser.
    Returns a datetime object if a date is found, otherwise None.
    """
    log.info(f"Searching for temporal expressions in text, relative to {base_time.isoformat()}")
    # Use search_dates to find all potential date strings in the text.
    # PREFER_DATES_FROM: 'past' ensures that "Friday" is interpreted as last Friday, not next Friday.
    # RELATIVE_BASE: Provides the anchor for relative times like "yesterday" or "2 hours ago".
    # STRICT_PARSING is added to prevent dateparser from misinterpreting common
    # words (like 'no' for November) as dates.
    # To handle relative dates with times (e.g., "yesterday at 10am") correctly,
    # we tell dateparser to prefer the time from the string over the base_time.
    found_dates = dateparser_search.search_dates(
        text,
        settings={
            'PREFER_DATES_FROM': 'past',
            'RELATIVE_BASE': base_time,
            'STRICT_PARSING': True,
        }
    )

    if found_dates:
        # search_dates returns a list of tuples: (string, datetime_object)
        first_match_str, first_match_dt = found_dates[0]
        log.info(f"Found potential event time: '{first_match_str}' -> {first_match_dt.isoformat()}")
        return first_match_dt
    else:
        log.info("No explicit event time found in text.")
        return None

def write_to_csv(data_row):
    """Appends a new data row to the master CSV file."""
    log.info(f"Writing to CSV: {data_row}")
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        file_exists = os.path.isfile(DATA_FILE)
        # Add 'Origin' and 'BoundingBox' to the fieldnames
        fieldnames = ['Title', 'Latitude', 'Longitude', 'Timestamp', 'Description', 'SourceURL', 'VideoURL', 'Agency', 'Origin', 'BoundingBox']
        with open(DATA_FILE, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')

            if not file_exists:
                writer.writeheader()
                log.info(f"Created new CSV file with headers: {DATA_FILE}")
            writer.writerow(data_row)
        log.info("Successfully wrote to CSV.")
    except Exception as e:
        log.error(f"Error writing to CSV file {DATA_FILE}: {e}", exc_info=True)

def process_sighting_text(post_text, source_url, post_timestamp_utc, agency='ICE', context=None, origin=None):
    """
    Processes the text of a sighting, geocodes it, and stores it.
    Deduplicates based on a combination of the source URL and the normalized
    post text to avoid processing the same content multiple times.
    """
    log.info(f"Processing text from source: {source_url} with context: {context}")

    if not nlp:
        log.error("spaCy model not loaded, cannot process text.")
        return 0

    # --- Deduplication based on Source URL and content ---
    existing_entries = set()
    if os.path.isfile(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    # Check if both columns exist to avoid KeyErrors
                    if 'SourceURL' in row and 'Description' in row:
                        # Normalize the description from the CSV for a fair comparison
                        normalized_desc = normalize_text(row['Description'])
                        existing_entries.add((row['SourceURL'], normalized_desc))
        except Exception as e:
            log.error(f"Could not read existing CSV data for deduplication: {e}", exc_info=True)

    # Normalize the incoming post_text to check for duplicates
    normalized_post_text = normalize_text(post_text)
    if (source_url, normalized_post_text) in existing_entries:
        log.warning(f"Duplicate post: Source {source_url} with the same content has already been processed. Skipping.")
        return 0

    doc = nlp(post_text)
    locations = [ent.text for ent in doc.ents if ent.label_ in ["CHI_LOCATION", "GPE", "LOC"]]
    log.info(f"Extracted {len(locations)} potential locations: {locations}")

    processed_count = 0
    for loc in locations:
        # Use the new normalization for the geocoding query
        geocoding_loc = normalize_text(loc)
        # Use title case for display purposes
        display_loc = loc.title()

        coords = geocode_location(geocoding_loc, context=context)
        if coords:
            # --- Temporal Extraction ---
            # Convert the post's creation time from a UTC timestamp to a datetime object.
            post_creation_time = datetime.fromtimestamp(post_timestamp_utc)

            # Try to extract a more specific event time from the text.
            event_time = extract_event_timestamp(post_text, post_creation_time)

            # If no specific time is found in the text, fall back to the post's creation time.
            final_timestamp = event_time if event_time else post_creation_time

            # Format the final timestamp into the required ISO format.
            timestamp_iso = final_timestamp.isoformat() + 'Z'

            # Serialize the bounding box dictionary to a JSON string for CSV storage
            bounding_box_json = json.dumps(coords.get('bounding_box')) if coords.get('bounding_box') else ''

            data_row = {
                'Title': f"Sighting near {display_loc}",
                'Latitude': coords['lat'],
                'Longitude': coords['lng'],
                'Timestamp': timestamp_iso,
                'Description': post_text,
                'SourceURL': source_url,
                'VideoURL': '',
                'Agency': agency,
                'Origin': origin,
                'BoundingBox': bounding_box_json
            }
            write_to_csv(data_row)
            processed_count += 1
            log.info(f"Successfully processed first valid location '{display_loc}'. Halting search for this source.")
            break # Exit after processing the first valid location

    return processed_count