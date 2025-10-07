import spacy
import requests
import csv
import os
from datetime import datetime
from src.logger import log # Import our new centralized logger

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

DATA_FILE = 'data/map_data.csv'

def geocode_location(location_text):
    """Converts a location string to geographic coordinates using Google Geocoding API."""
    log.info(f"Geocoding location: '{location_text}'")
    if not GOOGLE_API_KEY:
        log.error("Google API key not configured. Cannot geocode.")
        return None

    params = {
        'address': location_text,
        'key': GOOGLE_API_KEY,
    }
    try:
        response = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params=params)
        response.raise_for_status()
        results = response.json().get('results')
        if results:
            location = results[0]['geometry']['location']
            log.info(f"Geocoded '{location_text}' to {location}")
            return {"lat": location['lat'], "lng": location['lng']}
        else:
            log.warning(f"No geocoding results found for '{location_text}'")
            return None
    except requests.exceptions.RequestException as e:
        log.error(f"Failed to geocode '{location_text}'. Error: {e}", exc_info=True)
        return None

def write_to_csv(data_row):
    """Appends a new data row to the master CSV file."""
    log.info(f"Writing to CSV: {data_row}")
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        file_exists = os.path.isfile(DATA_FILE)
        with open(DATA_FILE, 'a', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Title', 'Latitude', 'Longitude', 'Timestamp', 'Description', 'SourceURL', 'VideoURL', 'Agency']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()
                log.info(f"Created new CSV file with headers: {DATA_FILE}")
            writer.writerow(data_row)
        log.info("Successfully wrote to CSV.")
    except Exception as e:
        log.error(f"Error writing to CSV file {DATA_FILE}: {e}", exc_info=True)

def process_sighting_text(post_text, source_url, post_timestamp_utc, agency='ICE'):
    """
    Processes the text of a sighting, geocodes it, and stores it.
    Deduplicates based on the source URL to avoid processing the same post multiple times.
    """
    log.info(f"Processing text from source: {source_url}")

    if not nlp:
        log.error("spaCy model not loaded, cannot process text.")
        return 0

    # --- Deduplication based on Source URL ---
    existing_source_urls = set()
    if os.path.isfile(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if 'SourceURL' in row:
                        existing_source_urls.add(row['SourceURL'])
        except Exception as e:
            log.error(f"Could not read existing CSV data for deduplication: {e}", exc_info=True)

    if source_url in existing_source_urls:
        log.warning(f"Duplicate post: Source {source_url} has already been processed. Skipping.")
        return 0

    doc = nlp(post_text)
    locations = [ent.text for ent in doc.ents if ent.label_ in ["CHI_LOCATION", "GPE", "LOC"]]
    log.info(f"Extracted {len(locations)} potential locations: {locations}")

    processed_count = 0
    for loc in locations:
        coords = geocode_location(loc)
        if coords:
            # Use the post's original creation timestamp
            timestamp_iso = datetime.fromtimestamp(post_timestamp_utc).isoformat() + 'Z'

            data_row = {
                'Title': f"Sighting near {loc}",
                'Latitude': coords['lat'],
                'Longitude': coords['lng'],
                'Timestamp': timestamp_iso,
                'Description': post_text,
                'SourceURL': source_url,
                'VideoURL': '',
                'Agency': agency
            }
            write_to_csv(data_row)
            processed_count += 1

    return processed_count