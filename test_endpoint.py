import requests
import json
import os
import time
import csv
import subprocess

# --- Test Configuration ---
URL = "http://localhost:8080/process-sighting"
TEST_DATA = {
    "post_text": "There was a sighting somewhere in Illinois.",
    "source_url": "http://example.com/sighting-report-approximate"
}
# Use a separate CSV file for testing to avoid modifying production data
TEST_CSV_FILE = 'data/test_map_data.csv'
LOG_FILE = 'src/debug.log'

def run_test():
    """
    Runs the test against the /process-sighting endpoint.
    """
    print("--- Starting Endpoint Test ---")

    # 1. Send POST request
    try:
        print(f"Sending POST request to {URL} with data:")
        print(json.dumps(TEST_DATA, indent=2))
        response = requests.post(URL, json=TEST_DATA, timeout=15)
        response.raise_for_status()
        print(f"Response received: {response.status_code}")
        print("Response JSON:", response.json())
    except requests.exceptions.RequestException as e:
        print(f"!!! TEST FAILED: Could not connect to the server. Error: {e}")
        print("!!! Please ensure the Flask application is running.")
        raise # Re-raise the exception to be caught by the main block

    # 2. Verify response
    if response.status_code != 200:
        print(f"!!! TEST FAILED: Expected status code 200, but got {response.status_code} ---")
        raise AssertionError("Test failed due to unexpected status code.")

    print("--- Test Result: SUCCESS (HTTP 200 OK) ---")

    # 3. Verify CSV file creation and content
    print("\n--- Verifying CSV Output ---")
    if not os.path.exists(TEST_CSV_FILE):
        print(f"!!! TEST FAILED: '{TEST_CSV_FILE}' was not created. ---")
        raise AssertionError("Test failed because output CSV was not created.")

    print(f"SUCCESS: '{TEST_CSV_FILE}' created.")
    with open(TEST_CSV_FILE, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        print("CSV Content:")
        print(json.dumps(rows, indent=2))

        # --- Verification Checks ---
        is_correct_row_count = len(rows) == 1
        bounding_box_str = rows[0].get('BoundingBox', '') if is_correct_row_count else ''
        is_bounding_box_valid = '"northeast"' in bounding_box_str and '"southwest"' in bounding_box_str

        if not (is_correct_row_count and is_bounding_box_valid):
            print("!!! TEST FAILED: CSV content verification failed.")
            if not is_correct_row_count:
                print(f"    - FAIL: Expected 1 data row, but found {len(rows)}.")
            if not is_bounding_box_valid:
                print(f"    - FAIL: BoundingBox data not found or is not valid. Found: '{bounding_box_str}'")
            raise AssertionError("Test failed due to incorrect CSV content.")

    print("--- Test Result: SUCCESS (CSV content verified) ---")

if __name__ == "__main__":
    server_process = None
    try:
        # 1. Setup: Ensure the test CSV does not exist from a previous failed run
        if os.path.exists(TEST_CSV_FILE):
            os.remove(TEST_CSV_FILE)

        # 2. Start the server as a subprocess with the correct environment
        print("--- Starting Flask server for test ---")
        test_env = os.environ.copy()
        test_env['FLASK_ENV'] = 'test'
        test_env['CSV_OUTPUT_FILE'] = TEST_CSV_FILE

        server_process = subprocess.Popen(
            ['python3', '-m', 'src.app'],
            env=test_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        # Give the server a moment to start
        time.sleep(3)

        # 3. Run the actual test
        run_test()

    except Exception as e:
        print(f"\n--- A test error occurred: {e} ---")
    finally:
        # 4. Teardown: Ensure the server is stopped and the test file is cleaned up
        print("\n--- Running Test Teardown ---")
        if server_process:
            print("Terminating server process...")
            server_process.terminate()
            server_process.wait()
            print("Server process terminated.")

        if os.path.exists(TEST_CSV_FILE):
            os.remove(TEST_CSV_FILE)
            print(f"Removed test file: {TEST_CSV_FILE}")

        # Print server logs for debugging if they exist
        if server_process:
            stdout, stderr = server_process.communicate()
            print("\n--- Server STDOUT ---")
            print(stdout.decode())
            print("\n--- Server STDERR ---")
            print(stderr.decode())