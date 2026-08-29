#!/usr/bin/env python3
"""One-time Spotify authorization for the voice assistant (headless / no browser
on the Pi).

Produces ~/.spotify_cache — the exact token cache that spotify.py reads. Run it
once; afterwards SpotifyController.connect() finds the cached token and refreshes
it automatically.

Usage:
    export SPOTIFY_CLIENT_ID='...'
    export SPOTIFY_CLIENT_SECRET='...'
    python3 spotify_auth.py
"""
import os
import sys

import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Must match spotify.py exactly:
SCOPE = (
    'user-read-playback-state '
    'user-modify-playback-state '
    'user-read-currently-playing'
)
REDIRECT_URI = os.environ.get(
    'SPOTIFY_REDIRECT_URI', 'http://127.0.0.1:8888/callback'
)
CACHE_PATH   = os.path.expanduser('~/.spotify_cache')
DEVICE_NAME  = 'Chochko'


def main():
    cid = os.environ.get('SPOTIFY_CLIENT_ID')
    sec = os.environ.get('SPOTIFY_CLIENT_SECRET')
    if not cid or not sec:
        sys.exit('Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET first.')

    auth = SpotifyOAuth(
        client_id=cid,
        client_secret=sec,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        open_browser=False,
        cache_path=CACHE_PATH,
    )

    # If a valid cache already exists, skip straight to verification.
    token = auth.get_cached_token()
    if not token:
        url = auth.get_authorize_url()
        print('\n1. Open this URL in a browser on ANY machine (phone/laptop):\n')
        print('   ' + url)
        print('\n2. Log in and approve. Your browser will then try to load a')
        print('   http://127.0.0.1:8888/callback?code=... page that FAILS to')
        print('   load — that is expected (nothing is listening on the Pi).')
        print('   Copy the ENTIRE address-bar URL of that failed page.\n')
        redirected = input('3. Paste the full redirected URL here: ').strip()
        code = auth.parse_response_code(redirected)
        auth.get_access_token(code, as_dict=False)
        print(f'\nToken cached to {CACHE_PATH}')
    else:
        print(f'Existing valid token found at {CACHE_PATH}')

    # ── Verify end to end ───────────────────────────────────────────────
    sp = spotipy.Spotify(auth_manager=auth)
    me = sp.me()
    print(f'\nAuthorized as: {me.get("display_name")} '
          f'({me.get("product")})')           # should say "premium"

    devices = sp.devices().get('devices', [])
    names = [d['name'] for d in devices]
    print(f'Visible Spotify devices: {names or "(none)"}')

    if any(DEVICE_NAME.lower() in n.lower() for n in names):
        print(f'\n✓ "{DEVICE_NAME}" is visible — voice assistant can target it.')
    else:
        print(f'\n✗ "{DEVICE_NAME}" not visible yet. Make sure raspotify is '
              f'running (systemctl status raspotify) and that it is logged in to '
              f'the SAME account you just authorized. The device often only '
              f'appears after it has played once from the phone app.')


if __name__ == '__main__':
    main()