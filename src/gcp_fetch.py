import requests
import os
import json
import re
from src.logger import log

# --- Configuration ---
API_KEY = os.getenv("GOOGLE_API_KEY")
CUSTOM_SEARCH_ENGINE_ID = os.getenv("CUSTOM_SEARCH_ENGINE_ID")
PROCESSING_ENDPOINT_URL = "http://localhost:8080/process-sighting"

# The query to search for. This can be refined over time.
SEARCH_QUERY = "ICE OR CBP OR \"Border Patrol\" sighting in Chicago"


def extract_subreddit_from_url(url: str) -> str | None:
    """Extracts the subreddit name from a Reddit URL."""
    if not url:
        return None
    match = re.search(r"reddit\.com/r/([^/]+)", url)
    if match:
        return match.group(1)
    return None


def format_reddit_json_url(url: str) -> str:
    """Appends .json to the end of the main part of a Reddit URL."""
    if url.endswith(".json"):
        return url

    # Remove trailing slash if it exists
    if url.endswith("/"):
        url = url[:-1]

    # Find the position of query parameters
    query_index = url.find("?")
    if query_index != -1:
        # Insert .json before the query string
        return f"{url[:query_index]}.json{url[query_index:]}"
    else:
        # Append .json to the end
        return f"{url}.json"


def get_all_comment_bodies(comments_data: list) -> str:
    """Recursively extracts all comment bodies from the Reddit API JSON response."""
    all_comments_text = ""
    for comment in comments_data:
        # We only care about actual comments (kind: t1)
        if comment.get("kind") == "t1":
            body = comment.get("data", {}).get("body")
            # Ensure the comment has a body and isn't deleted/removed
            if body and body not in ["[deleted]", "[removed]"]:
                all_comments_text += body + "\n"

            # Recursively process replies
            replies = comment.get("data", {}).get("replies")
            if replies and isinstance(replies, dict): # Replies is a Listing object
                all_comments_text += get_all_comment_bodies(
                    replies.get("data", {}).get("children", [])
                )
    return all_comments_text


def fetch_reddit_thread_text(reddit_url: str) -> str | None:
    """
    Fetches the full text content (post + comments) of a Reddit thread
    using its JSON API.
    """
    json_url = format_reddit_json_url(reddit_url)
    log.info(f"Attempting to fetch full content from Reddit JSON API: {json_url}")
    try:
        # Reddit API requests that clients set a unique User-Agent
        headers = {"User-Agent": "chicago-ice-map-bot/1.0"}
        response = requests.get(json_url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        # --- Extract post data ---
        # The first element of the list is the post's listing
        post_data = data[0]["data"]["children"][0]["data"]
        post_title = post_data.get("title", "")
        post_selftext = post_data.get("selftext", "")

        # --- Extract comments data ---
        # The second element is the comments' listing
        comments_data = data[1]["data"]["children"]
        comments_text = get_all_comment_bodies(comments_data)

        full_text = f"{post_title}\n\n{post_selftext}\n\n{comments_text}".strip()
        log.info(
            f"Successfully fetched and parsed full content for {reddit_url}. "
            f"Total length: {len(full_text)}"
        )
        return full_text

    except requests.exceptions.RequestException as e:
        log.warning(f"Failed to fetch Reddit JSON from {json_url}: {e}")
    except (IndexError, KeyError, TypeError) as e:
        log.warning(
            f"Failed to parse Reddit JSON structure from {json_url}. "
            f"It might not be a valid post URL or the structure is unexpected. Error: {e}"
        )
    return None


def fetch_and_process_data():
    """
    Fetches data from the Google Custom Search API, enriches Reddit links with
    full thread content, and sends it to the processing endpoint.
    """
    log.info("--- Starting data ingestion from Google Custom Search API ---")

    if not API_KEY or not CUSTOM_SEARCH_ENGINE_ID:
        log.critical("Google API Key or Custom Search Engine ID is not set. Aborting.")
        return

    # --- Make the API call to Google Custom Search ---
    search_url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": API_KEY,
        "cx": CUSTOM_SEARCH_ENGINE_ID,
        "q": SEARCH_QUERY,
        "sort": "date",  # Sort by date to get the most recent results
    }

    try:
        response = requests.get(search_url, params=params, timeout=15)
        response.raise_for_status()
        search_results = response.json()
        items = search_results.get("items", [])
        log.info(f"Retrieved {len(items)} items from the search API.")

    except requests.exceptions.RequestException as e:
        log.error(f"Failed to fetch data from Google Custom Search API: {e}", exc_info=True)
        return

    # --- Process each search result ---
    for item in items:
        try:
            source_url = item.get("link")
            # Default text is the snippet from the search result
            post_text = f"{item.get('title', '')}\n{item.get('snippet', '')}"

            # If it's a Reddit URL, try to fetch the full content
            if source_url and "reddit.com" in source_url:
                full_text = fetch_reddit_thread_text(source_url)
                if full_text:
                    post_text = full_text
                else:
                    log.warning(
                        f"Could not fetch full Reddit content for {source_url}. "
                        "Falling back to Google Search snippet."
                    )

            # Prepare the payload for our processing service
            payload = {
                "post_text": post_text,
                "source_url": source_url,
                # Use the extracted subreddit as context to help with geocoding
                "context": extract_subreddit_from_url(source_url),
            }

            log.info(
                f"Sending item to processing endpoint: {payload['source_url']} "
                f"with context: {payload['context']}"
            )

            # Send the data to our Flask app's endpoint
            proc_response = requests.post(
                PROCESSING_ENDPOINT_URL, json=payload, timeout=20
            )
            proc_response.raise_for_status()

            log.info(f"Processing response: {proc_response.json().get('message')}")

        except requests.exceptions.RequestException as e:
            log.error(
                f"Failed to send data to processing endpoint for URL {item.get('link')}: {e}",
                exc_info=True,
            )
            continue  # Move to the next item
        except Exception as e:
            log.error(
                f"An unexpected error occurred while processing item {item.get('link')}: {e}",
                exc_info=True,
            )
            continue


if __name__ == "__main__":
    fetch_and_process_data()
    log.info("--- Data ingestion process finished ---")