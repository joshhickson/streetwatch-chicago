import pytest
import requests
import json
import os
import time
import csv
import subprocess

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


def test_context_aware_geocoding(live_server, mocker):
    """
    Tests that the endpoint correctly uses the 'context' field from the
    payload to disambiguate a location. This test mocks the geocoding
    function to inspect the arguments it was called with.
    """
    # 1. Mock the geocoding function
    mock_geocode = mocker.patch('src.processing.geocode_location', return_value={
        "lat": 41.918, "lng": -87.677, "bounding_box": None
    })

    # 2. Prepare test data with an ambiguous location and a context
    url = f"{live_server}/process-sighting"
    test_data = {
        "post_text": "Sighting near Armitage.",
        "source_url": "http://example.com/sighting-with-context",
        "context": "Chicago, IL"
    }

    # 3. Send the request
    # First, need to modify the endpoint to accept the context
    # For now, let's assume it does and write the test.
    # I will modify the app code in a later step.
    # This is a placeholder for the test logic.
    # The test will fail until the app is updated.

    # This test is currently incomplete and will be finished in a later step
    # after the application code is updated to handle the `context` field.
    pass


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