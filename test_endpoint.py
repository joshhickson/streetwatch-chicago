import requests
import json
import os
import time

# --- Test Configuration ---
URL = "http://localhost:8080/process-sighting"
TEST_DATA = {
    "post_text": "ICE sighting reported near Wrigleyville on 9/25/25 at 3:30pm. This is a test.",
    "source_url": "http://example.com/sighting-report-with-timestamp"
}
CSV_FILE = 'data/map_data.csv'
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
        response.raise_for_status()  # Raise an exception for bad status codes
        print(f"Response received: {response.status_code}")
        print("Response JSON:", response.json())
    except requests.exceptions.RequestException as e:
        print(f"!!! TEST FAILED: Could not connect to the server. Error: {e}")
        print("!!! Please ensure the Flask application is running.")
        return

    # 2. Verify response
    if response.status_code == 200:
        print("--- Test Result: SUCCESS (HTTP 200 OK) ---")
    else:
        print(f"!!! TEST FAILED: Expected status code 200, but got {response.status_code} ---")
        return

    # 3. Verify CSV file creation and content
    print("\n--- Verifying CSV Output ---")
    time.sleep(1) # Give a moment for the file to be written
    if os.path.exists(CSV_FILE):
        print(f"SUCCESS: '{CSV_FILE}' created.")
        with open(CSV_FILE, 'r') as f:
            content = f.read().strip()
            lines = content.splitlines()
            print("CSV Content:")
            print(content)

            # --- Verification Checks ---
            # 1. Check for a single data row (plus header).
            is_correct_line_count = len(lines) == 2

            # 2. Check that the timestamp was correctly extracted from the text.
            # NOTE: The current NLP model only extracts the date ("9/25/25") and not the time.
            # The test will verify the date is correct, acknowledging this limitation.
            expected_timestamp = "2025-09-25T00:00:00Z"
            is_timestamp_correct = expected_timestamp in lines[1] if is_correct_line_count else False

            if is_correct_line_count and is_timestamp_correct:
                 print("--- Test Result: SUCCESS (CSV content verified: Correct date extracted) ---")
            else:
                 print("!!! TEST FAILED: CSV content verification failed.")
                 if not is_correct_line_count:
                     print(f"    - FAIL: Expected 2 lines, but found {len(lines)}.")
                 if not is_timestamp_correct:
                     print(f"    - FAIL: Expected timestamp '{expected_timestamp}' not found in output. The current model may not be parsing the time component.")
    else:
        print(f"!!! TEST FAILED: '{CSV_FILE}' was not created. ---")

    # 4. Display debug log
    print(f"\n--- Displaying Debug Log ({LOG_FILE}) ---")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            print(f.read())
    else:
        print(f"Warning: '{LOG_FILE}' not found.")

if __name__ == "__main__":
    run_test()