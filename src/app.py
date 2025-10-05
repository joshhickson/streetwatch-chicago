from flask import Flask, request, jsonify
from processing import process_sighting_text, debug_log

app = Flask(__name__)

@app.route('/process-sighting', methods=['POST'])
def handle_process_sighting():
    """
    Flask endpoint to process a sighting from a POST request.
    """
    debug_log("Received request for /process-sighting.")
    data = request.get_json()
    if not data or 'post_text' not in data:
        debug_log("Invalid input, 'post_text' is required.")
        return jsonify({"error": "Invalid input, 'post_text' is required."}), 400

    post_text = data.get('post_text')
    source_url = data.get('source_url', '')

    # Call the refactored processing function
    processed_count = process_sighting_text(post_text, source_url)

    response_message = f"Successfully processed and stored {processed_count} sightings."
    debug_log(f"Sending response: {response_message}")
    return jsonify({"message": response_message})

if __name__ == '__main__':
    debug_log("Starting Flask development server.")
    # Note: When running locally, ensure GOOGLE_GEOCODE_API_KEY is set as an environment variable.
    app.run(debug=True, host='0.0.0.0', port=8080)