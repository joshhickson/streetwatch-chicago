from flask import Flask, request, jsonify
from datetime import datetime
from src.processing import process_sighting_text
from src.logger import log # Import our new centralized logger

app = Flask(__name__)

@app.route('/process-sighting', methods=['POST'])
def handle_process_sighting():
    """
    Flask endpoint to process a sighting from a POST request.
    """
    log.info("Received POST request for /process-sighting.")
    data = request.get_json()
    if not data or 'post_text' not in data:
        log.error("Invalid input: 'post_text' is required in the JSON payload.")
        return jsonify({"error": "Invalid input, 'post_text' is required."}), 400

    post_text = data.get('post_text')
    source_url = data.get('source_url', 'N/A')
    log.info(f"Processing sighting from source: {source_url}")

    # Call the refactored processing function
    try:
        # Get the current time as the timestamp
        post_timestamp_utc = datetime.now().timestamp()

        # The context is not provided in this simple endpoint, so we pass None.
        # The test data is specific enough ("... at Millennium Park, Chicago.")
        # that it should be geocoded correctly without additional context.
        processed_count = process_sighting_text(
            post_text=post_text,
            source_url=source_url,
            post_timestamp_utc=post_timestamp_utc,
            context=None
        )
        response_message = f"Successfully processed and stored {processed_count} new sightings."
        log.info(f"Sending response: {response_message}")
        return jsonify({"message": response_message})
    except Exception as e:
        log.critical(f"An unhandled exception occurred in process_sighting_text: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred."}), 500


if __name__ == '__main__':
    log.info("Starting Flask development server.")
    # Note: When running locally, ensure PYTHONPATH is set to the project root
    # and GOOGLE_GEOCODE_API_KEY is set as an environment variable.
    app.run(debug=True, host='0.0.0.0', port=8080)