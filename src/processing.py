import spacy
import requests
import csv
import os
import json
import string
import hashlib
from datetime import datetime
from dateparser import search as dateparser_search
from elasticsearch import Elasticsearch
from src.logger import log

# --- Constants ---
# --- Helper Functions ---
def normalize_text(text: str) -> str:
    if not isinstance(text, str): return ""
    return text.lower().translate(str.maketrans('', '', string.punctuation))

# --- Model and API Configuration ---
CUSTOM_MODEL_PATH = 'models/custom_ner_model/model-best'
nlp = None
if os.path.exists(CUSTOM_MODEL_PATH):
    try:
        nlp = spacy.load(CUSTOM_MODEL_PATH)
        log.info(f"Custom spaCy model loaded from {CUSTOM_MODEL_PATH}.")
    except Exception as e:
        log.error(f"Error loading custom spaCy model from {CUSTOM_MODEL_PATH}: {e}", exc_info=True)
if nlp is None:
    log.warning("Custom model not found or failed to load. Falling back to 'en_core_web_sm'.")
    try:
        nlp = spacy.load("en_core_web_sm")
        log.info("Default spaCy model 'en_core_web_sm' loaded.")
    except Exception as e:
        log.critical(f"Failed to load default spaCy model: {e}", exc_info=True)
        nlp = None

GOOGLE_API_KEY = os.getenv("GOOGLE_GEOCODE_API_KEY")
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
ES_INDEX = os.getenv("ELASTICSEARCH_INDEX", "ice-sighting-map-data")
MOCK_ES_DIR = "tmp/es_mock"

# --- Elasticsearch Client Initialization ---
_es_client = None
def get_es_client():
    global _es_client
    if _es_client is None and os.getenv('INTEGRATION_TESTING') != 'true':
        try:
            _es_client = Elasticsearch(ES_HOST)
            if not _es_client.ping(): raise ConnectionError("Could not connect to Elasticsearch.")
            log.info(f"Successfully connected to Elasticsearch at {ES_HOST}")
        except Exception as e:
            log.critical(f"Failed to connect to Elasticsearch: {e}", exc_info=True)
            _es_client = None
    return _es_client

# --- Core Functions ---
def geocode_location(location_text, context=None):
    if os.getenv('INTEGRATION_TESTING') == 'true':
        log.info(f"INTEGRATION_TESTING mode: Returning mock geocode for location='{location_text}' with context='{context}'")
        return {"lat": 40.6331249, "lng": -89.3985283, "bounding_box": {"northeast": {"lat": 42.508338, "lng": -87.524529}, "southwest": {"lat": 36.970298, "lng": -91.513079}}}

    if not GOOGLE_API_KEY:
        log.error("Google API key not configured. Cannot geocode.")
        return None
    full_address = f"{location_text}, {context}" if context and context.strip() else location_text
    try:
        response = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params={'address': full_address, 'key': GOOGLE_API_KEY})
        response.raise_for_status()
        results = response.json().get('results')
        if results:
            geom = results[0].get('geometry', {})
            loc = geom.get('location', {})
            geocoded = {"lat": loc.get('lat'), "lng": loc.get('lng'), "bounding_box": None}
            if geom.get('location_type') == 'APPROXIMATE':
                geocoded['bounding_box'] = geom.get('viewport')
            return geocoded
        return None
    except requests.exceptions.RequestException as e:
        log.error(f"Failed to geocode '{full_address}': {e}", exc_info=True)
        return None

def extract_event_timestamp(text, base_time):
    found_dates = dateparser_search.search_dates(text, settings={'PREFER_DATES_FROM': 'past', 'RELATIVE_BASE': base_time, 'STRICT_PARSING': True})
    return found_dates[0][1] if found_dates else None

def store_sighting(doc_id, data_row):
    if os.getenv('INTEGRATION_TESTING') == 'true':
        os.makedirs(MOCK_ES_DIR, exist_ok=True)
        with open(os.path.join(MOCK_ES_DIR, f"{doc_id}.json"), 'w') as f:
            json.dump(data_row, f)
        log.info(f"INTEGRATION_TESTING mode: Wrote document {doc_id} to file.")
    else:
        es_client = get_es_client()
        if not es_client:
            log.error("Elasticsearch client not available. Cannot store sighting.")
            return
        try:
            es_doc = {
                "title": data_row.get("Title"), "description": data_row.get("Description"),
                "source_url": data_row.get("SourceURL"), "video_url": data_row.get("VideoURL"),
                "agency": data_row.get("Agency"), "origin": data_row.get("Origin"),
                "timestamp": data_row.get("Timestamp"),
                "location": {"lat": float(data_row.get("Latitude")), "lon": float(data_row.get("Longitude"))},
                "bounding_box": json.loads(data_row.get("BoundingBox")) if data_row.get("BoundingBox") else None
            }
            es_client.index(index=ES_INDEX, id=doc_id, document=es_doc)
            log.info(f"Successfully indexed document {doc_id} to index '{ES_INDEX}'.")
        except Exception as e:
            log.error(f"Failed to index document into Elasticsearch: {e}", exc_info=True)

def extract_event_trigger(entity_span):
    token = entity_span.root
    for _ in range(4):
        token = token.head
        if token.ent_type_ == 'ORG': continue
        if token.pos_ in ('VERB', 'NOUN'): return token.lemma_.title()
        if token.head is token: break
    return "Sighting"

def process_sighting_text(post_text, source_url, post_timestamp_utc, agency='ICE', context=None, origin=None):
    if not nlp:
        log.error("spaCy model is not available. Aborting processing.")
        return 0

    normalized_post_text = normalize_text(post_text)
    doc_id_hash = hashlib.sha256(f"{source_url}{normalized_post_text}".encode()).hexdigest()

    # Deduplication check
    if os.getenv('INTEGRATION_TESTING') == 'true':
        if os.path.exists(os.path.join(MOCK_ES_DIR, f"{doc_id_hash}.json")):
            log.warning(f"Duplicate post (file mock): ID {doc_id_hash} already exists. Skipping.")
            return 0
    else:
        es_client = get_es_client()
        if not es_client:
            log.error("Elasticsearch not available for deduplication check. Aborting.")
            return 0
        try:
            if es_client.exists(index=ES_INDEX, id=doc_id_hash):
                log.warning(f"Duplicate post (ES): ID {doc_id_hash} already exists. Skipping.")
                return 0
        except Exception as e:
            log.error(f"Failed to check for document existence in Elasticsearch: {e}", exc_info=True)
            return 0

    doc = nlp(post_text)
    locations = [ent for ent in doc.ents if ent.label_ in ["CHI_LOCATION", "GPE", "LOC"]]
    if not locations:
        return 0

    loc_span = locations[0]
    geocoding_loc = normalize_text(loc_span.text)
    coords = geocode_location(geocoding_loc, context=context)

    if coords:
        post_creation_time = datetime.fromtimestamp(post_timestamp_utc)
        event_time = extract_event_timestamp(post_text, post_creation_time)
        final_timestamp = event_time or post_creation_time

        data_row = {
            'Title': f"{extract_event_trigger(loc_span)} near {loc_span.text.title()}",
            'Latitude': coords['lat'], 'Longitude': coords['lng'],
            'Timestamp': final_timestamp.isoformat() + 'Z',
            'Description': post_text, 'SourceURL': source_url, 'VideoURL': '',
            'Agency': agency, 'Origin': origin,
            'BoundingBox': json.dumps(coords.get('bounding_box')) if coords.get('bounding_box') else ''
        }

        store_sighting(doc_id_hash, data_row)
        log.info(f"Successfully processed first valid location '{loc_span.text}'. Halting search.")
        return 1

    return 0