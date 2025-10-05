import spacy
import requests
import csv
import os
from datetime import datetime, timedelta
from haversine import haversine, Unit

# --- Manual Debug Logging ---
def debug_log(message):
    with open('src/debug.log', 'a') as f:
        f.write(f"{datetime.now()}: {message}\n")

# Define model paths
CUSTOM_MODEL_PATH = 'models/custom_ner_model/model-best'

# Load the spaCy model, preferring the custom model if it exists.
nlp = None
if os.path.exists(CUSTOM_MODEL_PATH):
    try:
        nlp = spacy.load(CUSTOM_MODEL_PATH)
        debug_log(f"Custom spaCy model loaded successfully from {CUSTOM_MODEL_PATH}.")
    except Exception as e:
        debug_log(f"Error loading custom spaCy model from {CUSTOM_MODEL_PATH}: {e}")

if nlp is None:
    debug_log("Custom model not found or failed to load. Falling back to default 'en_core_web_sm' model.")
    try:
        nlp = spacy.load("en_core_web_sm")
        debug_log("Default spaCy model 'en_core_web_sm' loaded successfully.")
    except Exception as e:
        debug_log(f"CRITICAL: Failed to load even the default spaCy model: {e}")
        # nlp remains None

# Constants
GOOGLE_API_KEY = os.getenv("GOOGLE_GEOCODE_API_KEY")
if not GOOGLE_API_KEY:
    debug_log("CRITICAL: GOOGLE_GEOCODE_API_KEY environment variable not set.")

DATA_FILE = 'data/map_data.csv'
DEDUPLICATION_DISTANCE_METERS = 200
DEDUPLICATION_TIME_HOURS = 1

def geocode_location(location_text):
    debug_log(f"Geocoding location: {location_text}")
    if not GOOGLE_API_KEY:
        debug_log("Google API key not configured. Cannot geocode.")
        return None

    params = {
        'address': location_text,
        'key': GOOGLE_API_KEY,
    }
    try:
        response = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params=params)
        response.raise_for_status()  # Raise an exception for bad status codes
        results = response.json().get('results')
        if results:
            location = results[0]['geometry']['location']
            debug_log(f"Geocoded {location_text} to {location}")
            return {"lat": location['lat'], "lng": location['lng']}
        else:
            debug_log(f"No results found for {location_text}")
            return None
    except requests.exceptions.RequestException as e:
        debug_log(f"Failed to geocode {location_text}. Error: {e}")
        return None

def is_duplicate(new_sighting, existing_sightings):
    """
    Checks if a new sighting is a duplicate of an existing one.
    """
    new_coords = (new_sighting['Latitude'], new_sighting['Longitude'])
    new_time = datetime.fromisoformat(new_sighting['Timestamp'].replace('Z', ''))

    for old_sighting in existing_sightings:
        old_coords = (float(old_sighting['Latitude']), float(old_sighting['Longitude']))
        old_time = datetime.fromisoformat(old_sighting['Timestamp'].replace('Z', ''))

        distance = haversine(new_coords, old_coords, unit=Unit.METERS)
        time_diff = abs(new_time - old_time)

        if distance < DEDUPLICATION_DISTANCE_METERS and time_diff < timedelta(hours=DEDUPLICATION_TIME_HOURS):
            debug_log(f"Duplicate found: New sighting at {new_coords} is too close to existing sighting at {old_coords}.")
            return True

    return False

def write_to_csv(data_row):
    debug_log(f"Writing to CSV: {data_row}")
    try:
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        file_exists = os.path.isfile(DATA_FILE)
        with open(DATA_FILE, 'a', newline='') as csvfile:
            fieldnames = ['Title', 'Latitude', 'Longitude', 'Timestamp', 'Description', 'SourceURL', 'VideoURL', 'Agency']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()
            writer.writerow(data_row)
        debug_log("Successfully wrote to CSV.")
    except Exception as e:
        debug_log(f"Error writing to CSV: {e}")

def process_sighting_text(post_text, source_url, agency='ICE'):
    """
    Processes the text of a sighting, geocodes it, and stores it.
    Returns the number of new sightings processed.
    """
    debug_log(f"Processing text: {post_text}")

    if not nlp:
        debug_log("spaCy model not loaded, cannot process text.")
        return 0

    # Read existing data for deduplication
    existing_sightings = []
    if os.path.isfile(DATA_FILE):
        with open(DATA_FILE, 'r') as csvfile:
            try:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    existing_sightings.append(row)
            except Exception as e:
                debug_log(f"Could not read existing CSV data: {e}")


    doc = nlp(post_text)
    # Look for our custom label first, but also accept the default spaCy location labels.
    locations = [ent.text for ent in doc.ents if ent.label_ in ["CHI_LOCATION", "GPE", "LOC"]]
    debug_log(f"Extracted locations: {locations}")

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
                debug_log(f"Skipping duplicate sighting: {data_row['Title']}")

    return processed_count