import pytest
from unittest.mock import MagicMock
from datetime import datetime
import requests
import os

# Make sure the app's source is in the path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src import processing

# --- Mocks and Test Data ---

MOCK_GEOCODE_SUCCESS = {
    "results": [
        {
            "geometry": {
                "location": {"lat": 41.881832, "lng": -87.623177},
                "location_type": "ROOFTOP",
            }
        }
    ],
    "status": "OK",
}

MOCK_GEOCODE_APPROXIMATE = {
    "results": [
        {
            "geometry": {
                "location": {"lat": 40.6331249, "lng": -89.3985283},
                "location_type": "APPROXIMATE",
                "viewport": {
                    "northeast": {"lat": 42.508338, "lng": -87.524529},
                    "southwest": {"lat": 36.970298, "lng": -91.513079},
                },
            }
        }
    ],
    "status": "OK",
}

MOCK_GEOCODE_ZERO_RESULTS = {"results": [], "status": "ZERO_RESULTS"}


# --- Tests for geocode_location ---

def test_geocode_location_success(mocker):
    """Tests a successful geocoding lookup."""
    mocker.patch('src.processing.GOOGLE_API_KEY', 'DUMMY_API_KEY')
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_GEOCODE_SUCCESS
    mock_get = mocker.patch("requests.get", return_value=mock_response)

    result = processing.geocode_location("Millennium Park")

    assert result is not None
    assert result["lat"] == 41.881832
    assert result["lng"] == -87.623177
    assert result["bounding_box"] is None
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs['params']['address'] == "Millennium Park"

def test_geocode_location_approximate_with_bounding_box(mocker):
    """Tests that a bounding box is correctly extracted for approximate results."""
    mocker.patch('src.processing.GOOGLE_API_KEY', 'DUMMY_API_KEY')
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_GEOCODE_APPROXIMATE
    mocker.patch("requests.get", return_value=mock_response)

    result = processing.geocode_location("Illinois")

    assert result is not None
    assert result["bounding_box"] is not None
    assert "northeast" in result["bounding_box"]

def test_geocode_location_no_results(mocker):
    """Tests the case where the API returns zero results."""
    mocker.patch('src.processing.GOOGLE_API_KEY', 'DUMMY_API_KEY')
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_GEOCODE_ZERO_RESULTS
    mocker.patch("requests.get", return_value=mock_response)

    result = processing.geocode_location("asdfasdfasdf")
    assert result is None

# --- Tests for extract_event_timestamp ---

@pytest.mark.parametrize("text, expected_date_parts", [
    ("Sighting happened on 9/25/25 12:50pm", (2025, 9, 25, 12, 50)),
    ("Event occurred yesterday at 10am", (2025, 10, 6, 10, 0)),
    ("This occurred last Friday", (2025, 10, 3, 0, 0)),
    ("A plain string with no date.", None),
])
def test_extract_event_timestamp(text, expected_date_parts):
    """Tests the temporal extraction logic with various date/time formats."""
    base_time = datetime(2025, 10, 7, 12, 0)
    result = processing.extract_event_timestamp(text, base_time)

    if expected_date_parts:
        expected_date = datetime(*expected_date_parts)
        assert result is not None
        assert result.year == expected_date.year
        assert result.month == expected_date.month
        assert result.day == expected_date.day
        assert result.hour == expected_date.hour
    else:
        assert result is None