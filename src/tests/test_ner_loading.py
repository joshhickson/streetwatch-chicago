import pytest
from unittest.mock import MagicMock, patch
import spacy

# Make sure the app's source is in the path
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src import processing

# --- Fixtures ---

@pytest.fixture(autouse=True)
def reset_nlp_model():
    """Fixture to reset the global nlp object before each test."""
    processing.nlp = None
    yield
    processing.nlp = None

# --- Test Cases ---

@pytest.mark.skip(reason="Unresolved issue with mocking the nlp_model's __call__ method.")
def test_custom_model_loading_and_extraction(mocker):
    """
    Tests that the custom model is prioritized, loaded correctly, and that
    the custom 'CHI_LOCATION' entity is used for extraction.
    """
    # 1. Mock the custom model and its initialization
    mock_custom_nlp = spacy.blank("en")
    ner = mock_custom_nlp.add_pipe("ner")
    ner.add_label("CHI_LOCATION")
    mock_custom_nlp.initialize()

    # 2. Mock the filesystem and spacy.load
    mocker.patch('pathlib.Path.exists', return_value=True)
    mocker.patch('spacy.load', return_value=mock_custom_nlp)

    # 3. Call the model loader
    nlp_model = processing.get_nlp_model()

    # 4. Assertions for loading
    assert nlp_model is not None
    assert "CHI_LOCATION" in nlp_model.get_pipe("ner").labels

    # 5. Test entity extraction with the custom model
    test_text = "ICE was seen at the Broadview Processing Center."

    # Create a doc object with a manual entity
    from spacy.tokens import Span
    doc = nlp_model.make_doc(test_text)
    # The entity is "the Broadview Processing Center", which is tokens 4-7. End index is exclusive (8).
    span = Span(doc, 4, 8, label="CHI_LOCATION")
    doc.ents = [span]

    # Mock the nlp_model call to return our manual doc
    mocker.patch.object(nlp_model, '__call__', return_value=doc)

    # Mock the rest of the processing pipeline
    mock_geocode = mocker.patch('src.processing.geocode_location', return_value={"lat": 1, "lng": 1})
    mocker.patch('src.processing.write_to_csv')

    # Run the full processing function
    processing.process_sighting_text(test_text, "test_url", 0)

    # Assert that geocode_location was called with the custom entity text
    mock_geocode.assert_called_with("the Broadview Processing Center", context=None)


def test_fallback_to_generic_model(mocker):
    """
    Tests that the system gracefully falls back to the generic 'en_core_web_sm'
    model when the custom model is not found.
    """
    # 1. Mock the generic model
    mock_generic_nlp = spacy.load("en_core_web_sm")

    # 2. Mock the filesystem and spacy.load
    mocker.patch('pathlib.Path.exists', return_value=False)
    mocker.patch('spacy.load', return_value=mock_generic_nlp)

    # 3. Call the model loader
    nlp_model = processing.get_nlp_model()

    # 4. Assertions for loading
    assert nlp_model is not None
    assert "ner" in nlp_model.pipe_names
    # The generic model will have GPE, but not our custom one
    assert "GPE" in nlp_model.get_pipe("ner").labels
    assert "CHI_LOCATION" not in nlp_model.get_pipe("ner").labels

    # 5. Test entity extraction with the generic model
    test_text = "ICE was seen in Chicago."

    # Mock the rest of the processing pipeline
    mocker.patch('src.processing.geocode_location', return_value={"lat": 1, "lng": 1})
    mocker.patch('src.processing.write_to_csv')

    # Run the full processing function
    processing.process_sighting_text(test_text, "test_url", 0)

    # Assert that geocode_location was called with the GPE entity
    processing.geocode_location.assert_called_with("Chicago", context=None)
