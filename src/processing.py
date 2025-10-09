import spacy
import requests
import csv
import os
import json
from datetime import datetime
from dateparser import search as dateparser_search, parse as dateparser_parse
from src.logger import log

# --- Model and API Configuration ---
GOOGLE_API_KEY = os.getenv("GOOGLE_GEOCODE_API_KEY")
DATA_FILE = os.getenv('CSV_OUTPUT_FILE', 'data/map_data.csv')

# --- Global variable for the model, initialized to None ---
nlp = None

# --- Geographic Context Mapping ---
SUBREDDIT_CONTEXT_MAP = {
    "chicago": "Chicago, IL, USA",
    "EyesOnIce": "USA",
    "nyc": "New York, NY, USA",
    "bayarea": "Bay Area, CA, USA"
}

def get_nlp_model():
    """
    Lazy-loads the spaCy model. It's only loaded the first time this function is called.
    """
    global nlp
    if nlp is None:
        log.info("NLP model not loaded yet. Attempting to load 'en_core_web_sm'...")
        try:
            nlp = spacy.load("en_core_web_sm")
            log.info("Default spaCy model 'en_core_web_sm' loaded successfully.")
        except Exception as e:
            log.critical(f"Failed to load 'en_core_web_sm' model. NLP processing will be disabled. Error: {e}", exc_info=True)
            nlp = None
    return nlp

def get_geocoding_hint(context: str) -> str:
    """Returns a high-quality geographic hint based on the subreddit context."""
    if not context: return ""
    return SUBREDDIT_CONTEXT_MAP.get(context.lower(), context)

def normalize_text(text: str) -> str:
    """Normalizes a string by converting it to title case and stripping whitespace."""
    return text.strip().title()

def geocode_location(location_text, context=None):
    """Converts a location string to geographic coordinates using Google Geocoding API."""
    if os.getenv('INTEGRATION_TESTING') == 'true':
        log.info(f"INTEGRATION_TESTING mode: Returning mock geocode for location='{location_text}' with context='{context}'")
        return {"lat": 40.6331249, "lng": -89.3985283, "bounding_box": {"northeast": {"lat": 42.508338, "lng": -87.524529}, "southwest": {"lat": 36.970298, "lng": -91.513079}}}

    geo_hint = get_geocoding_hint(context)
    full_address = f"{location_text}, {geo_hint}" if geo_hint else location_text
    log.info(f"Geocoding location: '{full_address}'")

    if not GOOGLE_API_KEY:
        log.error("Google API key not configured. Cannot geocode.")
        return None

    params = {'address': full_address, 'key': GOOGLE_API_KEY}
    try:
        response = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params=params)
        response.raise_for_status()
        results = response.json().get('results')
        if results:
            result = results[0]
            geometry = result.get('geometry', {})
            location = geometry.get('location', {})
            lat, lng = location.get('lat'), location.get('lng')

            if not lat or not lng:
                log.warning(f"Geocoding result for '{full_address}' missing lat/lng.")
                return None

            geocoded_data = {"lat": lat, "lng": lng, "bounding_box": None}
            if geometry.get('location_type') == 'APPROXIMATE':
                if viewport := geometry.get('viewport'):
                    geocoded_data['bounding_box'] = viewport
            return geocoded_data
        else:
            log.warning(f"No geocoding results found for '{full_address}'")
            return None
    except requests.exceptions.RequestException as e:
        log.error(f"Failed to geocode '{full_address}'. Error: {e}", exc_info=True)
        return None

def extract_event_timestamp(text, base_time):
    """Extracts a timestamp from text using a robust two-step dateparser approach."""
    found_dates = dateparser_search.search_dates(text, settings={'PREFER_DATES_FROM': 'past', 'RELATIVE_BASE': base_time})
    if not found_dates:
        return None
    for date_str, _ in found_dates:
        if len(date_str.strip()) <= 3: continue
        final_dt = dateparser_parse(date_str, settings={'PREFER_DATES_FROM': 'past', 'RELATIVE_BASE': base_time})
        if final_dt:
            return final_dt
    return None

def write_to_csv(data_row):
    """Appends a new data row to the master CSV file."""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    file_exists = os.path.isfile(DATA_FILE)
    fieldnames = ['Title', 'Latitude', 'Longitude', 'Timestamp', 'Description', 'SourceURL', 'VideoURL', 'Agency', 'Origin', 'BoundingBox']
    with open(DATA_FILE, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        writer.writerow(data_row)

def process_sighting_text(post_text, source_url, post_timestamp_utc, agency='ICE', context=None, origin=None):
    """Processes the text of a sighting, geocodes it, and stores it."""
    log.info(f"Processing text from source: {source_url} with context: {context}")

    # Call the lazy-loader to ensure the model is ready.
    nlp_model = get_nlp_model()
    if not nlp_model:
        log.error("NLP model is not available. Cannot process text.")
        return 0

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

    doc = nlp_model(post_text)
    # The custom CHI_LOCATION label is removed as we are now only using the generic model.
    locations = [ent.text for ent in doc.ents if ent.label_ in ["GPE", "LOC"]]
    log.info(f"Extracted {len(locations)} potential locations: {locations}")

    processed_count = 0
    for loc in locations:
        normalized_loc = normalize_text(loc)
        coords = geocode_location(normalized_loc, context=context)
        if coords:
            post_creation_time = datetime.fromtimestamp(post_timestamp_utc)
            event_time = extract_event_timestamp(post_text, post_creation_time)
            final_timestamp = event_time if event_time else post_creation_time
            timestamp_iso = final_timestamp.isoformat() + 'Z'
            bounding_box_json = json.dumps(coords.get('bounding_box')) if coords.get('bounding_box') else ''
            data_row = {
                'Title': f"Sighting near {normalized_loc}", 'Latitude': coords['lat'], 'Longitude': coords['lng'],
                'Timestamp': timestamp_iso, 'Description': post_text, 'SourceURL': source_url,
                'VideoURL': '', 'Agency': agency, 'Origin': origin, 'BoundingBox': bounding_box_json
            }
            write_to_csv(data_row)
            processed_count += 1
            log.info(f"Successfully processed first valid location '{normalized_loc}'. Halting search for this source.")
            break
    return processed_count