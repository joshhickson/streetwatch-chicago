import praw
import os
import time
from datetime import datetime
from src.processing import process_sighting_text
from src.logger import log # Import our new centralized logger

# --- Reddit API Configuration ---
CLIENT_ID = os.getenv("REDDIT_API_ID")
CLIENT_SECRET = os.getenv("REDDIT_API_SECRET")
USER_AGENT = os.getenv("REDDIT_USER_AGENT", "StreetWatchBot:v1.0 by /u/YourUsername")

# --- Search Configuration ---
SUBREDDITS = ['chicago', 'AskChicago', 'illinois', 'eyesonice']
KEYWORDS = ['ice', 'cbp', 'cpd', 'border patrol', 'raid', 'checkpoint']
AGENCY_STRING = 'ICE, CBP, CPD'
SEARCH_WINDOW_SECONDS = 3600 # Suitable for an hourly cron job.

def initialize_reddit():
    """Initializes and returns a PRAW Reddit instance."""
    if not CLIENT_ID or not CLIENT_SECRET:
        log.critical("CRITICAL: Reddit API credentials (REDDIT_API_ID, REDDIT_API_SECRET) are not set. Halting process.")
        return None

    try:
        reddit = praw.Reddit(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            user_agent=USER_AGENT
        )
        log.info(f"PRAW Reddit instance created. Read-only status: {reddit.read_only}")
        return reddit
    except Exception as e:
        log.critical(f"Error initializing PRAW Reddit instance: {e}", exc_info=True)
        return None

def fetch_and_process_reddit_data():
    """Fetches new posts from specified subreddits based on keywords and processes them."""
    log.info("--- Starting scheduled Reddit data fetch ---")
    reddit = initialize_reddit()
    if not reddit:
        return

    processed_permalinks = set()
    current_time_utc = datetime.utcnow().timestamp()
    total_new_sightings = 0

    for sub_name in SUBREDDITS:
        try:
            subreddit = reddit.subreddit(sub_name)
            log.info(f"Searching subreddit: r/{sub_name}")

            search_query = ' OR '.join(f'"{k}"' for k in KEYWORDS)

            for post in subreddit.search(search_query, sort='new', time_filter='hour'):
                if (current_time_utc - post.created_utc) < SEARCH_WINDOW_SECONDS and post.permalink not in processed_permalinks:

                    full_text = f"Title: {post.title}. Body: {post.selftext}"
                    log.info(f"Found potential sighting in post: https://www.reddit.com{post.permalink}")

                    new_sightings_count = process_sighting_text(
                        post_text=full_text,
                        source_url=f"https://www.reddit.com{post.permalink}",
                        post_timestamp_utc=post.created_utc,
                        agency=AGENCY_STRING
                    )

                    if new_sightings_count > 0:
                        log.info(f"Successfully processed {new_sightings_count} new sightings from post.")
                        total_new_sightings += new_sightings_count

                    processed_permalinks.add(post.permalink)
                    time.sleep(2) # Be a good API citizen

        except Exception as e:
            log.error(f"An error occurred while processing subreddit r/{sub_name}: {e}", exc_info=True)

    log.info(f"--- Finished scheduled Reddit data fetch. Total new sightings found: {total_new_sightings} ---")

if __name__ == '__main__':
    fetch_and_process_reddit_data()