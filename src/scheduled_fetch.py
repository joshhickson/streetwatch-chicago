import praw
import os
import time
from datetime import datetime
from processing import process_sighting_text, debug_log

# --- Reddit API Configuration ---
# Credentials will be stored as GitHub secrets and passed as environment variables
CLIENT_ID = os.getenv("REDDIT_API_ID")
CLIENT_SECRET = os.getenv("REDDIT_API_SECRET")
# A descriptive user agent is required by Reddit's API rules.
USER_AGENT = os.getenv("REDDIT_USER_AGENT", "StreetWatchBot:v1.0 by /u/YourUsername")

# --- Search Configuration ---
SUBREDDITS = ['chicago', 'AskChicago']
KEYWORDS = ['ice', 'cbp', 'cpd', 'border patrol', 'raid', 'checkpoint']
AGENCY_STRING = 'ICE, CBP, CPD'
# Search for posts within the last hour. This is suitable for an hourly cron job.
SEARCH_WINDOW_SECONDS = 3600

def initialize_reddit():
    """
    Initializes and returns a PRAW Reddit instance.
    Returns None if credentials are not configured.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        debug_log("CRITICAL: Reddit API credentials (REDDIT_API_ID, REDDIT_API_SECRET) are not set.")
        return None

    try:
        reddit = praw.Reddit(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            user_agent=USER_AGENT
        )
        # A simple check to ensure the connection is valid
        debug_log(f"Reddit instance created. Read-only status: {reddit.read_only}")
        return reddit
    except Exception as e:
        debug_log(f"Error initializing PRAW Reddit instance: {e}")
        return None

def fetch_and_process_reddit_data():
    """
    Fetches new posts from specified subreddits based on keywords and processes them.
    """
    debug_log("--- Starting scheduled Reddit data fetch ---")
    reddit = initialize_reddit()
    if not reddit:
        debug_log("Halting fetch process due to missing Reddit credentials.")
        return

    processed_permalinks = set()
    current_time_utc = datetime.utcnow().timestamp()

    for sub_name in SUBREDDITS:
        try:
            subreddit = reddit.subreddit(sub_name)
            debug_log(f"Searching subreddit: r/{sub_name}")

            # Combine keywords into a single search query. PRAW handles the OR logic.
            search_query = ' OR '.join(f'"{k}"' for k in KEYWORDS)

            # Use sort='new' and a time_filter to narrow down results from the API
            for post in subreddit.search(search_query, sort='new', time_filter='hour'):
                # Check if the post is within our precise time window and not already processed in this run
                if (current_time_utc - post.created_utc) < SEARCH_WINDOW_SECONDS and post.permalink not in processed_permalinks:

                    full_text = f"Title: {post.title}. Body: {post.selftext}"
                    debug_log(f"Found potential sighting in post: {post.permalink}")

                    # Use the refactored function to process the sighting
                    process_sighting_text(
                        post_text=full_text,
                        source_url=f"https://www.reddit.com{post.permalink}",
                        agency=AGENCY_STRING
                    )

                    processed_permalinks.add(post.permalink)

                    # Be a good API citizen and sleep between processing posts
                    time.sleep(2)

        except Exception as e:
            debug_log(f"An error occurred while processing subreddit r/{sub_name}: {e}")

    debug_log("--- Finished scheduled Reddit data fetch ---")

if __name__ == '__main__':
    fetch_and_process_reddit_data()