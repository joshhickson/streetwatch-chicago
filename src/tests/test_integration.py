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

def test_content_based_deduplication(live_server):
    """
    Tests the more precise deduplication logic which considers both the
    source URL and the normalized content of the post.
    """
    url = f"{live_server}/process-sighting"

    # --- Case 1: Initial Post (should be processed) ---
    payload1 = {"post_text": "First sighting in Chicago.", "source_url": "http://example.com/event-1"}
    response1 = requests.post(url, json=payload1, timeout=15)
    assert response1.status_code == 200
    assert "1" in response1.json()["message"]

    # --- Case 2: Exact Duplicate (should be skipped) ---
    response2 = requests.post(url, json=payload1, timeout=15)
    assert response2.status_code == 200
    assert "0" in response2.json()["message"]

    # --- Case 3: Same URL, Different Text (should be processed) ---
    # This is not a duplicate because the content has changed.
    payload3 = {"post_text": "Second sighting in Chicago.", "source_url": "http://example.com/event-1"}
    response3 = requests.post(url, json=payload3, timeout=15)
    assert response3.status_code == 200
    assert "1" in response3.json()["message"]

    # --- Case 4: Different URL, Same Text (should be processed) ---
    # This is not a duplicate because the source URL is different.
    payload4 = {"post_text": "First sighting in Chicago.", "source_url": "http://example.com/event-2"}
    response4 = requests.post(url, json=payload4, timeout=15)
    assert response4.status_code == 200
    assert "1" in response4.json()["message"]

    # --- Case 5: Same URL, Same Text w/ Punctuation (should be skipped) ---
    # This IS a duplicate because the text normalizes to the same content as payload 1.
    payload5 = {"post_text": "First sighting in Chicago!!", "source_url": "http://example.com/event-1"}
    response5 = requests.post(url, json=payload5, timeout=15)
    assert response5.status_code == 200
    assert "0" in response5.json()["message"]

    # --- Final Verification ---
    assert os.path.exists(TEST_CSV_FILE)
    with open(TEST_CSV_FILE, 'r', newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
        # We expect 3 entries: from payloads 1, 3, and 4.
        assert len(rows) == 3

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

    expected_log_line = "INTEGRATION_TESTING mode: Returning mock geocode for location='armitage' with context='Chicago, IL'"
    assert expected_log_line in stderr_content