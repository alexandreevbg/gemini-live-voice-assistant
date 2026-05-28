# spotify_auth.py
# Run ONCE manually to authorize Spotify
# After that, main.py uses the cached token automatically

import os
import sys
sys.path.insert(0, '/home/chochko/voiceAssist')
import spotipy
from spotipy.oauth2 import SpotifyOAuth

SCOPE = (
    'user-read-playback-state '
    'user-modify-playback-state '
    'user-read-currently-playing'
)

auth = SpotifyOAuth(
    client_id=os.environ['SPOTIFY_CLIENT_ID'],
    client_secret=os.environ['SPOTIFY_CLIENT_SECRET'],
    redirect_uri=os.environ.get(
        'SPOTIFY_REDIRECT_URI', 'http://127.0.0.1:8888/callback'
    ),
    scope=SCOPE,
    open_browser=False,
    cache_path=os.path.expanduser('~/.spotify_cache')
)

print('Open this URL in your browser:')
print()
print(auth.get_authorize_url())
print()
url = input('Paste the full redirect URL here: ').strip()
code = auth.parse_response_code(url)
token = auth.get_access_token(code, as_dict=True)
print()
print('Token cached successfully ✓')
print('You can now run main.py')