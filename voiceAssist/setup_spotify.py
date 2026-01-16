import os
import logging
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Configure logging
logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

def setup_spotify():
    print("--- Spotify Setup ---")
    
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

    if not client_id or not client_secret:
        print("Error: SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET not found in environment variables.")
        return

    cache_path = os.path.join(os.path.dirname(__file__), ".spotify_cache")
    
    print(f"Cache path: {cache_path}")
    print("Initializing authentication flow...")
    print("Please follow the instructions to authenticate.")
    print("-" * 60)
    print("NOTE: On your computer, copy the FULL URL from the address bar after redirection.")
    print("It will look like: http://127.0.0.1:8888/callback?code=AQD...")
    print("-" * 60)

    try:
        scope = "user-modify-playback-state user-read-playback-state"
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            open_browser=False,
            cache_path=cache_path
        ))
        user = sp.current_user()
        print(f"Successfully authenticated as: {user['display_name']}")
        print(f"Token cached at: {cache_path}")
    except Exception as e:
        print(f"Authentication failed: {e}")

if __name__ == "__main__":
    setup_spotify()