import pytest
import requests
import json
import os
import time
import csv
import subprocess
from src import gcp_fetch
import importlib

# --- Constants ---
BASE_URL = "http://localhost:8080"
TEST_CSV_FILE = 'data/test_map_data.csv'
STDERR_LOG_FILE = 'logs/test_stderr.log'

# --- Pytest Fixture for Server Management ---

@pytest.fixture(scope="function")
def live_server():
    """
    A pytest fixture that starts the Flask server in a subprocess for the
    duration of the test module, and handles teardown. It polls the /health
    endpoint to ensure the server is ready before running tests.
    """
    # 1. Setup: Clean up files from previous runs
    # Ensure a clean slate for each test run to prevent state leakage
    if os.path.exists(TEST_CSV_FILE):
        os.remove(TEST_CSV_FILE)
    os.makedirs(os.path.dirname(STDERR_LOG_FILE), exist_ok=True)
    if os.path.exists(STDERR_LOG_FILE):
        os.remove(STDERR_LOG_FILE)

    # 2. Start the server, redirecting stderr to a file
    server_process = None
    err_file = open(STDERR_LOG_FILE, 'wb')
    try:
        test_env = os.environ.copy()
        test_env['FLASK_ENV'] = 'test'
        test_env['CSV_OUTPUT_FILE'] = TEST_CSV_FILE
        # Set the integration testing flag to use mock responses in the app
        test_env['INTEGRATION_TESTING'] = 'true'

        server_process = subprocess.Popen(
            ['python3', '-m', 'src.app'],
            env=test_env,
            stdout=subprocess.PIPE,
            stderr=err_file
        )

        # Poll the /health endpoint to wait for the server to be ready
        max_wait_time = 20
        start_time = time.time()
        server_ready = False
        while time.time() - start_time < max_wait_time:
            if server_process.poll() is not None:
                pytest.fail(f"Server process terminated prematurely. Check {STDERR_LOG_FILE}.", pytrace=False)
            try:
                response = requests.get(f"{BASE_URL}/health", timeout=1)
                if response.status_code == 200:
                    print("\nServer is ready.")
                    server_ready = True
                    break
            except requests.ConnectionError:
                time.sleep(0.5)

        if not server_ready:
            pytest.fail(f"Server did not become ready in time. Check {STDERR_LOG_FILE}.", pytrace=False)

        # Yield control to the tests
        yield BASE_URL

    finally:
        # Teardown
        print("\n--- Running Test Teardown ---")
        if server_process:
            print("Terminating server process...")
            server_process.terminate()
            server_process.wait(timeout=5)

        err_file.close()
        # For debugging, print the stderr log
        if os.path.exists(STDERR_LOG_FILE):
            with open(STDERR_LOG_FILE, 'r') as f:
                print(f"\n--- Server STDERR from {STDERR_LOG_FILE} ---")
                print(f.read())
            os.remove(STDERR_LOG_FILE)

        if os.path.exists(TEST_CSV_FILE):
            os.remove(TEST_CSV_FILE)

# --- Test Functions ---

def test_process_sighting_endpoint(live_server):
    """
    Tests the /process-sighting endpoint with a basic request to ensure
    it processes data and creates a CSV file with the correct content.
    """
    # 1. Prepare Test Data and URL
    url = f"{live_server}/process-sighting"
    test_data = {
        "post_text": "There was a sighting somewhere in Illinois.",
        "source_url": "http://example.com/sighting-report-approximate"
    }

    # 2. Send POST request
    response = requests.post(url, json=test_data, timeout=15)

    # 3. Verify HTTP Response
    assert response.status_code == 200
    response_json = response.json()
    assert "message" in response_json
    assert "1" in response_json["message"]

    # 4. Verify CSV file content
    assert os.path.exists(TEST_CSV_FILE)

    with open(TEST_CSV_FILE, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        # Check for correct number of rows
        assert len(rows) == 1
        row = rows[0]
        assert row['SourceURL'] == test_data['source_url']

        # Check that a bounding box was created for the approximate location
        bounding_box_str = row.get('BoundingBox', '')
        assert bounding_box_str, "BoundingBox column should not be empty."

        bounding_box = json.loads(bounding_box_str)
        assert "northeast" in bounding_box
        assert "southwest" in bounding_box


def test_context_aware_geocoding(live_server):
    """
    Tests that the endpoint correctly uses the 'context' field from the
    payload by inspecting the server logs.
    """
    # 1. Prepare test data
    url = f"{live_server}/process-sighting"
    test_data = {
        "post_text": "Sighting near Armitage.",
        "source_url": "http://example.com/sighting-with-context",
        "context": "Chicago, IL"
    }

    # 2. Send the request
    response = requests.post(url, json=test_data, timeout=15)
    assert response.status_code == 200
    assert "1" in response.json()["message"]

    # 3. Verify the server log contains the correct context message
    assert os.path.exists(STDERR_LOG_FILE)
    with open(STDERR_LOG_FILE, 'r') as f:
        stderr_content = f.read()

    # The processing script normalizes the location text to 'Armitage'
    expected_log_line = "INTEGRATION_TESTING mode: Returning mock geocode for location='Armitage' with context='Chicago, IL'"
    assert expected_log_line in stderr_content


def test_deduplication_of_source_url(live_server):
    """
    Tests that sending the same source URL twice results in only one
    entry being created in the CSV file.
    """
    url = f"{live_server}/process-sighting"
    test_data = {
        "post_text": "A unique event in Chicago.",
        "source_url": "http://example.com/unique-sighting-1"
    }

    # Send the first request
    response1 = requests.post(url, json=test_data, timeout=15)
    assert response1.status_code == 200
    assert "1" in response1.json()["message"]

    # Send the exact same request again
    response2 = requests.post(url, json=test_data, timeout=15)
    assert response2.status_code == 200
    assert "0" in response2.json()["message"]

    # Verify CSV file content
    with open(TEST_CSV_FILE, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1


def test_temporal_extraction_from_text(live_server):
    """
    Tests that the endpoint correctly extracts a timestamp from the post text
    instead of just using the current time.
    """
    url = f"{live_server}/process-sighting"
    test_data = {
        "post_text": "Event happened on 9/25/25 12:50pm in Chicago.",
        "source_url": "http://example.com/sighting-with-timestamp"
    }

    # Send the request
    response = requests.post(url, json=test_data, timeout=15)
    assert response.status_code == 200
    assert "1" in response.json()["message"]

    # Verify the CSV content
    with open(TEST_CSV_FILE, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        # The test fixture now has module scope, so we need to find our specific row
        relevant_row = next((row for row in rows if row['SourceURL'] == test_data['source_url']), None)
        assert relevant_row is not None

        # Check that the timestamp was extracted from the text
        timestamp_str = relevant_row.get('Timestamp')
        assert timestamp_str is not None
        assert timestamp_str.startswith("2025-09-25T12:50:00")


def test_gcp_fetch_script(mocker):
    """
    Tests the gcp_fetch.py script's logic by mocking the external APIs,
    including the new Reddit JSON API call.
    """
    # 1. Mock the Google Custom Search API response
    mock_gcp_response = {
        "items": [
            {
                "title": "ICE sighting on Main St",
                "snippet": "A witness saw ICE agents on Main Street today.",
                "link": "https://www.reddit.com/r/chicago/comments/q12345/sighting-gcp-1/",
                "displayLink": "www.reddit.com"
            }
        ]
    }
    # 2. Mock the Reddit JSON API response
    mock_reddit_response = [
        {"data": {"children": [{"data": {"title": "ICE sighting on Main St", "selftext": "Original post body."}}]}},
        {"data": {"children": [
            {"kind": "t1", "data": {"body": "Here is the first comment.", "replies": ""}},
            {"kind": "t1", "data": {"body": "Here is the second comment.", "replies": ""}},
        ]}}
    ]

    # 3. Configure the mock for requests.get to return different values on each call
    mock_get = mocker.patch('requests.get')

    # Create mock response objects for each API call
    mock_gcp_api_response = mocker.MagicMock()
    mock_gcp_api_response.json.return_value = mock_gcp_response
    mock_gcp_api_response.raise_for_status.return_value = None

    mock_reddit_api_response = mocker.MagicMock()
    mock_reddit_api_response.json.return_value = mock_reddit_response
    mock_reddit_api_response.raise_for_status.return_value = None

    # The first call to get() gets the Google result, the second gets the Reddit result
    mock_get.side_effect = [mock_gcp_api_response, mock_reddit_api_response]

    # 4. Mock the POST call to our processing endpoint
    mock_post = mocker.patch('requests.post')
    mock_post.return_value.raise_for_status.return_value = None
    mock_post.return_value.json.return_value = {"message": "Successfully processed 1 new sightings."}

    # 5. Mock environment variables for the script
    mocker.patch.dict(os.environ, {
        "GOOGLE_API_KEY": "DUMMY_GCP_KEY",
        "CUSTOM_SEARCH_ENGINE_ID": "DUMMY_CX"
    })
    importlib.reload(gcp_fetch)

    # 6. Run the script's main function
    gcp_fetch.fetch_and_process_data()

    # 7. Assertions
    # Verify that requests.get was called twice
    assert mock_get.call_count == 2

    # Verify the first call was to the Google API
    google_call = mock_get.call_args_list[0]
    assert "https://www.googleapis.com/customsearch/v1" in google_call.args[0]

    # Verify the second call was to the Reddit JSON API
    reddit_call = mock_get.call_args_list[1]
    expected_reddit_url = "https://www.reddit.com/r/chicago/comments/q12345/sighting-gcp-1.json"
    assert expected_reddit_url in reddit_call.args[0]

    # Verify our endpoint was called once
    mock_post.assert_called_once()

    # Inspect the payload sent to our endpoint
    call_args, call_kwargs = mock_post.call_args
    payload = call_kwargs['json']

    assert payload['source_url'] == "https://www.reddit.com/r/chicago/comments/q12345/sighting-gcp-1/"

    # Check that the payload contains the full text from Reddit, not the snippet
    expected_full_text = (
        "ICE sighting on Main St\n\n"
        "Original post body.\n\n"
        "Here is the first comment.\n"
        "Here is the second comment."
    )
    assert payload['post_text'] == expected_full_text
    assert "A witness saw ICE agents" not in payload['post_text'] # Snippet should not be present

    # Verify context is still extracted correctly
    assert payload['context'] == "chicago"


@pytest.mark.skip(reason="Custom NER model loading is unstable and has been disabled pending further investigation.")
def test_custom_ner_model_location_extraction(live_server):
    """
    Tests that the custom NER model is being used and correctly extracts a
    Chicago-specific location that the generic model would likely miss.
    """
    # 1. Prepare test data with a location from our training set
    url = f"{live_server}/process-sighting"
    test_data = {
        "post_text": "Federal agents entering a house near Thomas Street and Harding Avenue.",
        "source_url": "http://example.com/custom-ner-sighting"
    }

    # 2. Send the request
    response = requests.post(url, json=test_data, timeout=15)
    assert response.status_code == 200
    assert "1" in response.json()["message"]

    # 3. Verify the CSV content shows the custom location was extracted
    assert os.path.exists(TEST_CSV_FILE)
    with open(TEST_CSV_FILE, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        # The processing script normalizes the location text to title case
        assert rows[0]['Title'] == 'Sighting near Thomas Street And Harding Avenue'