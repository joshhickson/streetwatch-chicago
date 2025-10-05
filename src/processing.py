import spacy
import requests
import csv
import os
from datetime import datetime, timedelta
from haversine import haversine, Unit
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
DEDUPLICATION_DISTANCE_METERS = 200
DEDUPLICATION_TIME_HOURS = 1

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

def is_duplicate(new_sighting, existing_sightings):
    """Checks if a new sighting is a duplicate of an existing one based on time and distance."""
    new_coords = (new_sighting['Latitude'], new_sighting['Longitude'])
    new_time = datetime.fromisoformat(new_sighting['Timestamp'].replace('Z', ''))

    for old_sighting in existing_sightings:
        try:
            old_coords = (float(old_sighting['Latitude']), float(old_sighting['Longitude']))
            old_time = datetime.fromisoformat(old_sighting['Timestamp'].replace('Z', ''))

            distance = haversine(new_coords, old_coords, unit=Unit.METERS)
            time_diff = abs(new_time - old_time)

            if distance < DEDUPLICATION_DISTANCE_METERS and time_diff < timedelta(hours=DEDUPLICATION_TIME_HOURS):
                log.info(f"Duplicate found: New sighting at {new_coords} is too close to existing sighting at {old_coords}.")
                return True
        except (ValueError, KeyError) as e:
            log.warning(f"Could not parse existing sighting for deduplication check. Row: {old_sighting}. Error: {e}")
            continue

    return False

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

def process_sighting_text(post_text, source_url, agency='ICE'):
    """
    Processes the text of a sighting, geocodes it, and stores it.
    Returns the number of new sightings processed.
    """
    log.info(f"Processing text from source: {source_url}")

    if not nlp:
        log.error("spaCy model not loaded, cannot process text.")
        return 0

    existing_sightings = []
    if os.path.isfile(DATA_FILE):
        with open(DATA_FILE, 'r', newline='', encoding='utf-8') as csvfile:
            try:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    existing_sightings.append(row)
            except Exception as e:
                log.error(f"Could not read existing CSV data for deduplication: {e}", exc_info=True)

    doc = nlp(post_text)
    locations = [ent.text for ent in doc.ents if ent.label_ in ["CHI_LOCATION", "GPE", "LOC"]]
    log.info(f"Extracted {len(locations)} potential locations: {locations}")

    processed_count = 0
    for loc in locations:
        coords = geocode_location(loc)
        if coords:
            data_row = {
                'Title': f"Sighting near {loc}",
                'Latitude': coords['lat'],
                'Longitude': coords['lng'],
                'Timestamp': datetime.utcnow().isoformat() + 'Z',
                'Description': post_text,
                'SourceURL': source_url,
                'VideoURL': '',
                'Agency': agency
            }

            if not is_duplicate(data_row, existing_sightings):
                write_to_csv(data_row)
                processed_count += 1
            else:
                log.warning(f"Skipping duplicate sighting: {data_row['Title']}")

    return processed_count