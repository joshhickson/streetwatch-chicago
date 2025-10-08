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
    A pytest fixture that starts the Flask server in a subprocess for each
    test function, redirecting stderr to a log file for inspection.
    """
    # 1. Setup: Clean up files from previous runs
    if os.path.exists(TEST_CSV_FILE):
        os.remove(TEST_CSV_FILE)
    # Create logs directory if it doesn't exist
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
        test_env['INTEGRATION_TESTING'] = 'true'

        server_process = subprocess.Popen(
            ['python3', '-m', 'src.app'],
            env=test_env,
            stdout=subprocess.PIPE,
            stderr=err_file
        )

        # Poll the /health endpoint to wait for the server to be ready
        max_wait_time = 15
        start_time = time.time()
        server_ready = False
        while time.time() - start_time < max_wait_time:
            if server_process.poll() is not None:
                pytest.fail("Server process terminated prematurely.", pytrace=False)

            try:
                response = requests.get(f"{BASE_URL}/health", timeout=1)
                if response.status_code == 200:
                    print("\nServer is ready.")
                    server_ready = True
                    break
            except requests.ConnectionError:
                time.sleep(0.5)

        if not server_ready:
            pytest.fail("Server did not become ready in time.", pytrace=False)

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

def test_process_sighting_with_approximate_location(live_server):
    """
    Tests the /process-sighting endpoint with text that results in an
    approximate location, verifying that a bounding box is created.
    This test relies on the INTEGRATION_TESTING env var being set by the fixture.
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

        assert len(rows) == 1
        row = rows[0]
        assert row['SourceURL'] == test_data['source_url']

        bounding_box_str = row.get('BoundingBox', '')
        assert bounding_box_str, "BoundingBox column should not be empty."

        bounding_box = json.loads(bounding_box_str)
        assert "northeast" in bounding_box
        assert "southwest" in bounding_box

def test_deduplication_of_source_url(live_server):
    """
    Tests that sending the same source URL twice results in only one
    entry being created in the CSV file.
    """
    # 1. Prepare Test Data and URL
    url = f"{live_server}/process-sighting"
    test_data = {
        "post_text": "A unique event in Chicago.",
        "source_url": "http://example.com/unique-sighting-1"
    }

    # 2. Send the first request
    response1 = requests.post(url, json=test_data, timeout=15)
    assert response1.status_code == 200
    assert "1" in response1.json()["message"]

    # 3. Send the exact same request again
    response2 = requests.post(url, json=test_data, timeout=15)
    assert response2.status_code == 200
    assert "0" in response2.json()["message"]

    # 4. Verify CSV file content
    assert os.path.exists(TEST_CSV_FILE)
    with open(TEST_CSV_FILE, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        assert len(rows) == 1
        assert rows[0]['SourceURL'] == test_data['source_url']

def test_temporal_extraction_from_text(live_server):
    """
    Tests that the endpoint correctly extracts a timestamp from the post text
    instead of just using the current time.
    """
    # 1. Prepare Test Data with a specific date
    url = f"{live_server}/process-sighting"
    test_data = {
        "post_text": "Event happened on 9/25/25 12:50pm at the Bean.",
        "source_url": "http://example.com/sighting-with-timestamp"
    }

    # 2. Send the request
    response = requests.post(url, json=test_data, timeout=15)
    assert response.status_code == 200
    assert "1" in response.json()["message"]

    # 3. Verify the CSV content
    assert os.path.exists(TEST_CSV_FILE)
    with open(TEST_CSV_FILE, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        assert len(rows) == 1
        relevant_row = rows[0]

        timestamp_str = relevant_row.get('Timestamp')
        assert timestamp_str is not None
        assert timestamp_str.startswith("2025-09-25T12:50:00")

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

    expected_log_line = "INTEGRATION_TESTING mode: Returning mock geocode for location='Armitage' with context='Chicago, IL'"
    assert expected_log_line in stderr_content