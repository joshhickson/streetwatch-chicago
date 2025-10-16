import spacy
import requests
import csv
import os
import json
from datetime import datetime
from pathlib import Path
from dateparser import search as dateparser_search, parse as dateparser_parse
from src.logger import log
from src.location_enhancer import (
    ChicagoLocationExtractor,
    is_likely_chicago_location,
    enhance_geocoding_query
)

# --- Model and API Configuration ---
GOOGLE_API_KEY = os.getenv("GOOGLE_GEOCODE_API_KEY")
DATA_FILE = os.getenv('CSV_OUTPUT_FILE', 'data/map_data.csv')
CUSTOM_MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "custom_ner_model"

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
    Lazy-loads the spaCy model. It prioritizes the custom model, falling back to the generic one.
    """
    global nlp
    if nlp is not None:
        return nlp

    log.info("NLP model not loaded yet. Attempting to load models...")
    # Attempt to load the custom model first
    if CUSTOM_MODEL_PATH.exists():
        try:
            log.info(f"Attempting to load custom NER model from: {CUSTOM_MODEL_PATH}")
            nlp = spacy.load(CUSTOM_MODEL_PATH)
            log.info("Custom NER model loaded successfully.")
            return nlp
        except Exception as e:
            log.warning(f"Failed to load custom NER model. Error: {e}", exc_info=True)
            # Fall through to loading the default model

    # If custom model fails or doesn't exist, load the default model
    log.info("Custom model not found or failed to load. Attempting to load 'en_core_web_sm'...")
    try:
        nlp = spacy.load("en_core_web_sm")
        log.info("Default spaCy model 'en_core_web_sm' loaded successfully.")
    except Exception as e:
        log.critical(f"Failed to load 'en_core_web_sm' model. NLP processing will be disabled. Error: {e}", exc_info=True)
        nlp = None

    return nlp

def get_geocoding_hint(context: str | None) -> str:
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

    # Use enhanced geocoding query
    geo_hint = get_geocoding_hint(context)
    full_address = enhance_geocoding_query(location_text, geo_hint)
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
    """Appends a new data row to the master CSV file with automatic backup."""
    from src.backup_csv import create_backup
    
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    file_exists = os.path.isfile(DATA_FILE)
    
    if file_exists:
        backup_path = create_backup(DATA_FILE)
        if backup_path:
            log.info(f"Backup created before write: {backup_path}")
    
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

    # ENHANCED: Use pattern-based extraction first
    location_extractor = ChicagoLocationExtractor()
    pattern_locations = location_extractor.extract_all_locations(post_text)
    prioritized_locations = location_extractor.prioritize_locations(pattern_locations)
    
    if prioritized_locations:
        log.info(f"Pattern extraction found {len(prioritized_locations)} locations: {prioritized_locations}")
    
    # Run NER model
    doc = nlp_model(post_text)

    # Dynamically set the location labels to look for
    accepted_labels = ["GPE", "LOC"]
    if 'ner' in nlp_model.pipe_names:
        ner_pipe = nlp_model.get_pipe('ner')
        if hasattr(ner_pipe, 'labels') and 'CHI_LOCATION' in ner_pipe.labels:  # type: ignore
            accepted_labels.append('CHI_LOCATION')
            log.info("Custom 'CHI_LOCATION' label found in model. Will use for extraction.")

    # Extract NER locations
    ner_locations = [ent.text for ent in doc.ents if ent.label_ in accepted_labels]
    
    # ENHANCED: Also check ORG entities that might be Chicago locations
    org_entities = [ent.text for ent in doc.ents if ent.label_ == 'ORG']
    for org_text in org_entities:
        if is_likely_chicago_location(org_text, 'ORG'):
            log.info(f"Found ORG entity '{org_text}' that's likely a Chicago location")
            ner_locations.append(org_text)
    
    log.info(f"NER extracted {len(ner_locations)} potential locations: {ner_locations}")

    # ENHANCED: Combine pattern-based and NER locations, prioritizing patterns
    all_locations = []
    seen = set()
    
    # Add pattern-based locations first (most reliable)
    for loc in prioritized_locations:
        loc_lower = loc.lower()
        if loc_lower not in seen:
            all_locations.append(loc)
            seen.add(loc_lower)
    
    # Add NER locations that aren't already found
    for loc in ner_locations:
        loc_lower = loc.lower()
        if loc_lower not in seen:
            all_locations.append(loc)
            seen.add(loc_lower)
    
    log.info(f"Combined extraction: {len(all_locations)} total locations to try: {all_locations}")

    processed_count = 0
    for loc in all_locations:
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
    
    if processed_count == 0:
        log.warning(f"No valid geocodable locations found for source: {source_url}")
    
    return processed_count