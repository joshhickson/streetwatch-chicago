import spacy
import requests
import os
import json
import string
import hashlib
import re
from datetime import datetime
from dateparser import search as dateparser_search
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from src.logger import log

# --- Constants & Config ---
MODELS_DIR = "models"
CUSTOM_MODEL_PATH = os.path.join(MODELS_DIR, 'custom_ner_model/model-best')
GOOGLE_API_KEY = os.getenv("GOOGLE_GEOCODE_API_KEY")
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
ES_INDEX = os.getenv("ELASTICSEARCH_INDEX", "ice-sighting-map-data")
MOCK_ES_DIR = "tmp/es_mock"
FAISS_INDEX_PATH = os.path.join(MODELS_DIR, "faiss_index.bin")
SIMILARITY_THRESHOLD = 0.1 # Adjusted for mock embeddings

# --- Helper Functions ---
def normalize_text(text: str) -> str:
    if not isinstance(text, str): return ""
    return text.lower().translate(str.maketrans('', '', string.punctuation))

def extract_video_url(text: str) -> str | None:
    """
    Finds the first URL from a list of common video platforms in a string.
    """
    if not isinstance(text, str):
        return None
    # Regex to find URLs from YouTube, Streamable, and Reddit's video service
    url_pattern = re.compile(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    )
    all_urls = url_pattern.findall(text)

    video_platforms = [
        "youtube.com", "youtu.be",
        "streamable.com",
        "v.redd.it"
    ]

    for url in all_urls:
        for platform in video_platforms:
            if platform in url:
                log.info(f"Found potential video URL: {url}")
                return url

    return None

# --- Lazy-loaded Clients & Models ---
_nlp = None
def get_nlp():
    global _nlp
    if _nlp is None:
        # Attempt to load the custom model first
        if os.path.exists(CUSTOM_MODEL_PATH):
            try:
                _nlp = spacy.load(CUSTOM_MODEL_PATH)
                log.info(f"Custom spaCy model loaded from {CUSTOM_MODEL_PATH}.")
                return _nlp
            except Exception as e:
                log.error(f"Error loading custom spaCy model: {e}", exc_info=True)

        # Fallback to the default model if the custom one fails or doesn't exist
        log.warning("Custom model not found or failed to load. Falling back to 'en_core_web_sm'.")
        try:
            _nlp = spacy.load("en_core_web_sm")
            log.info("Default spaCy model 'en_core_web_sm' loaded.")
        except Exception as e:
            log.critical(f"Failed to load default spaCy model: {e}", exc_info=True)
            # Ensure nlp is None if all loading fails
            _nlp = None
    return _nlp

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

class MockSbert:
    def get_sentence_embedding_dimension(self): return 5
    def encode(self, text):
        hash_val = int(hashlib.md5(normalize_text(text).encode()).hexdigest(), 16)
        vec = np.array([hash_val % 100] * 5, dtype='float32')
        return vec / np.linalg.norm(vec) if np.linalg.norm(vec) > 0 else vec

_sbert_model = None
def get_sbert_model():
    global _sbert_model
    if _sbert_model is None:
        if os.getenv('INTEGRATION_TESTING') == 'true':
            _sbert_model = MockSbert()
        else:
            try:
                _sbert_model = SentenceTransformer('all-MiniLM-L6-v2')
            except Exception as e:
                log.critical(f"Failed to load SentenceTransformer model: {e}", exc_info=True)
                _sbert_model = None
    return _sbert_model

_faiss_index = None
def get_faiss_index():
    global _faiss_index
    if _faiss_index is None:
        sbert_model = get_sbert_model()
        if sbert_model:
            embedding_dim = sbert_model.get_sentence_embedding_dimension()
            if os.path.exists(FAISS_INDEX_PATH) and os.getenv('INTEGRATION_TESTING') != 'true':
                try:
                    _faiss_index = faiss.read_index(FAISS_INDEX_PATH)
                except Exception as e:
                    _faiss_index = faiss.IndexFlatL2(embedding_dim)
            else:
                _faiss_index = faiss.IndexFlatL2(embedding_dim)
    return _faiss_index

# --- Core Processing Logic ---
def geocode_location(location_text, context=None):
    if os.getenv('INTEGRATION_TESTING') == 'true':
        return {"lat": 41.8781, "lng": -87.6298, "bounding_box": {"northeast": {"lat": 42.023, "lng": -87.524}, "southwest": {"lat": 41.644, "lng": -87.940}}}
    if not GOOGLE_API_KEY: return None
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
    except requests.exceptions.RequestException as e:
        log.error(f"Failed to geocode '{full_address}': {e}", exc_info=True)
    return None

def extract_event_timestamp(text, base_time):
    found_dates = dateparser_search.search_dates(text, settings={'PREFER_DATES_FROM': 'past', 'RELATIVE_BASE': base_time, 'STRICT_PARSING': True})
    return found_dates[0][1] if found_dates else None

def save_faiss_index():
    faiss_index = get_faiss_index()
    if faiss_index is not None:
        try:
            os.makedirs(MODELS_DIR, exist_ok=True)
            faiss.write_index(faiss_index, FAISS_INDEX_PATH)
        except Exception as e:
            log.error(f"Failed to save FAISS index: {e}", exc_info=True)

def find_similar_in_vector_index(embedding):
    faiss_index = get_faiss_index()
    if faiss_index is None or faiss_index.ntotal == 0: return False
    query_vector = np.array([embedding], dtype='float32')
    distances, _ = faiss_index.search(query_vector, 1)
    return distances.size > 0 and distances[0][0] < SIMILARITY_THRESHOLD

def add_to_vector_index(embedding):
    faiss_index = get_faiss_index()
    if faiss_index is not None:
        faiss_index.add(np.array([embedding], dtype='float32'))

def store_sighting(doc_id, data_row):
    if os.getenv('INTEGRATION_TESTING') == 'true':
        os.makedirs(MOCK_ES_DIR, exist_ok=True)
        with open(os.path.join(MOCK_ES_DIR, f"{doc_id}.json"), 'w') as f: json.dump(data_row, f)
    else:
        es_client = get_es_client()
        if not es_client: return
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
    nlp = get_nlp()
    if not nlp: return 0

    normalized_post_text = normalize_text(post_text)
    doc_id_hash = hashlib.sha256(f"{source_url}{normalized_post_text}".encode()).hexdigest()

    if os.getenv('INTEGRATION_TESTING') == 'true':
        if os.path.exists(os.path.join(MOCK_ES_DIR, f"{doc_id_hash}.json")): return 0
    else:
        es_client = get_es_client()
        if not es_client or es_client.exists(index=ES_INDEX, id=doc_id_hash): return 0

    sbert_model = get_sbert_model()
    if sbert_model:
        embedding = sbert_model.encode(normalized_post_text)
        if find_similar_in_vector_index(embedding):
            return 0

    doc = nlp(post_text)
    locations = [ent for ent in doc.ents if ent.label_ in ["CHI_LOCATION", "GPE", "LOC"]]
    if not locations: return 0

    loc_span = locations[0]
    coords = geocode_location(normalize_text(loc_span.text), context=context)

    if coords:
        final_timestamp = extract_event_timestamp(post_text, datetime.fromtimestamp(post_timestamp_utc)) or datetime.fromtimestamp(post_timestamp_utc)
        video_url = extract_video_url(post_text) or ""

        data_row = {
            'Title': f"{extract_event_trigger(loc_span)} near {loc_span.text.title()}",
            'Latitude': coords['lat'], 'Longitude': coords['lng'],
            'Timestamp': final_timestamp.isoformat() + 'Z',
            'Description': post_text, 'SourceURL': source_url, 'VideoURL': video_url,
            'Agency': agency, 'Origin': origin,
            'BoundingBox': json.dumps(coords.get('bounding_box')) if coords.get('bounding_box') else ''
        }
        store_sighting(doc_id_hash, data_row)

        if sbert_model and 'embedding' in locals():
            add_to_vector_index(embedding)
            save_faiss_index()

        return 1

    return 0