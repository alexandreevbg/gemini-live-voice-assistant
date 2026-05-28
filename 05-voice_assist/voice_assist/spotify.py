import logging
import os
import spotipy
import time
from spotipy.oauth2 import SpotifyOAuth

log = logging.getLogger(__name__)

SCOPE = (
    'user-read-playback-state '
    'user-modify-playback-state '
    'user-read-currently-playing'
)
DEVICE_NAME = 'Chochko'

class SpotifyController:
    def __init__(self):
        self._sp        = None
        self._device_id = None
        self.connected  = False

    def connect(self) -> bool:
        client_id     = os.environ.get('SPOTIFY_CLIENT_ID')
        client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
        redirect_uri  = os.environ.get(
            'SPOTIFY_REDIRECT_URI', 'http://127.0.0.1:8888/callback'
        )

        if not client_id or not client_secret:
            log.warning('Spotify credentials not set — disabled')
            return False

        try:
            auth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=SCOPE,
                open_browser=False,
                cache_path=os.path.expanduser('~/.spotify_cache')
            )
            token = auth.get_cached_token()
            if not token:
                log.warning('No cached Spotify token — run spotify_auth.py first')
                return False
            if auth.is_token_expired(token):
                token = auth.refresh_access_token(token['refresh_token'])

            self._sp       = spotipy.Spotify(auth=token['access_token'])
            self._auth     = auth
            self._token    = token
            self.connected = True

            # Try to find device — may not be ready yet after boot
            self._device_id = self._find_device()
            if self._device_id:
                log.info(f'Spotify connected — device found')
            else:
                log.info('Spotify connected — device not yet visible (will retry)')
            return True

        except Exception as e:
            log.warning(f'Spotify connection failed: {e}')
            self.connected = False
            return False

    def _refresh_token_if_needed(self):
        """Refresh OAuth token if expired."""
        try:
            if self._auth and self._auth.is_token_expired(self._token):
                self._token = self._auth.refresh_access_token(
                    self._token['refresh_token']
                )
                self._sp = spotipy.Spotify(auth=self._token['access_token'])
                log.info('Spotify token refreshed')
        except Exception as e:
            log.error(f'Token refresh error: {e}')

    def _find_device(self) -> str | None:
        try:
            self._refresh_token_if_needed()
            devices = self._sp.devices()
            log.debug(f'Devices: {[d["name"] for d in devices["devices"]]}')
            for d in devices['devices']:
                if DEVICE_NAME.lower() in d['name'].lower():
                    log.debug(f'Found Chochko: {d["id"][:8]}...')
                    return d['id']
            log.warning(f'Chochko not in: {[d["name"] for d in devices["devices"]]}')
            return None
        except Exception as e:
            log.error(f'Find device error: {e}')
            return None

    def _refresh_device(self):
        """Refresh device ID — retry if not found previously."""
        self._device_id = self._find_device()

    def _ensure_active(self) -> bool:
        """Always refresh device ID first, then transfer."""
        try:
            # Always refresh — never trust cached ID
            self._device_id = self._find_device()

            if not self._device_id:
                log.warning('Chochko device not found in Spotify')
                return False

            current = self._sp.current_playback()
            if current and current.get('device', {}).get('id') == self._device_id:
                return True  # already active

            log.info(f'Transferring playback to Chochko')
            self._sp.transfer_playback(
                device_id=self._device_id,
                force_play=False
            )
            time.sleep(1)
            return True

        except spotipy.exceptions.SpotifyException as e:
            if '404' in str(e):
                log.warning(f'Transfer failed 404 — device offline: {e}')
                self._device_id = None
            else:
                log.error(f'Ensure active error: {e}')
            return False
        except Exception as e:
            log.error(f'Ensure active error: {e}')
            return False

    def set_volume(self, percent: int):
        """Set Spotify volume 0-100."""
        if not self.connected:
            return
        try:
            self._ensure_active()
            if not self._device_id:
                log.warning("Cannot set volume: device ID not available.")
                return
            self._sp.volume(percent, device_id=self._device_id)
            log.info(f"Spotify volume set to {percent}% on device {self._device_id}.")
        except spotipy.exceptions.SpotifyException as e:
            if '404' in str(e):
                log.warning('Spotify volume: no active device — skipping')
            else:
                log.error(f'Spotify volume error: {e}')

    def pause(self):
        """Pause Spotify playback."""
        if not self.connected:
            return
        try:
            self._sp.pause_playback(device_id=self._device_id)
            log.debug(f"Attempting to pause playback on device {self._device_id}.")
            log.info('Spotify paused')
        except spotipy.exceptions.SpotifyException as e:
            log.warning(f'Spotify pause error: {e}')

    def resume(self):
        """Resume Spotify playback."""
        if not self.connected:
            return
        try:
            if not self._ensure_active():
                log.warning('Could not resume: device not found')
                return
            log.debug(f"Attempting to resume playback on device {self._device_id}.")
            self._sp.start_playback(device_id=self._device_id)
            log.info('Spotify resumed')
        except spotipy.exceptions.SpotifyException as e:
            log.warning(f'Spotify resume error: {e}')

    def next_track(self):
        """Skip to next track."""
        if not self.connected:
            return
        try:
            log.debug(f"Attempting to skip to next track on device {self._device_id}.")
            self._sp.next_track(device_id=self._device_id)
            log.info('Spotify next track')
        except Exception as e:
            log.error(f'Spotify next track error: {e}')

    def previous_track(self):
        """Go to previous track."""
        if not self.connected:
            return
        try:
            log.debug(f"Attempting to go to previous track on device {self._device_id}.")
            self._sp.previous_track(device_id=self._device_id)
            log.info('Spotify previous track')
        except Exception as e:
            log.error(f'Spotify previous track error: {e}')

    def play(self, query: str):
        """Search and play track/artist/playlist."""
        if not self.connected:
            return
        if not query:
            self.resume()
            return
        try:
            if not self._ensure_active():
                log.warning('Could not play: Chochko device not found')
                return
                
            results = self._sp.search(q=query, limit=1, type='track')
            tracks  = results['tracks']['items']
            log.debug(f"Spotify search for '{query}' returned {len(tracks)} tracks.")

            if not tracks:
                log.warning(f'No results for: {query}')
                return
            uri = tracks[0]['uri']
            self._sp.start_playback(
                device_id=self._device_id,
                uris=[uri]
            )
            log.info(f'Spotify playing: {tracks[0]["name"]}')
        except Exception as e:
            log.error(f'Spotify play error: {e}')

    def get_current_playback_device(self) -> dict | None:
        """Get information about the currently active playback device."""
        if not self.connected:
            return None
        try:
            current = self._sp.current_playback()
            if current and current.get('device'):
                return current['device']
        except Exception as e:
            log.error(f'Spotify get_current_playback_device error: {e}')
        return None

    def get_current(self) -> dict | None:
        """Get currently playing track info."""
        if not self.connected:
            return None
        try:
            current = self._sp.current_playback()
            if current and current.get('item'):
                return {
                    'track':  current['item']['name'],
                    'artist': current['item']['artists'][0]['name'],
                    'playing': current['is_playing']
                }
        except Exception as e:
            log.error(f'Spotify current error: {e}')
        return None
        
    def get_devices(self) -> list:
        """Get list of available Spotify devices."""
        if not self.connected:
            return []
        try:
            self._refresh_token_if_needed()
            devices = self._sp.devices()
            return [
                {
                    'name':   d['name'],
                    'id':     d['id'],
                    'active': d['is_active'],
                    'type':   d['type']
                }
                for d in devices.get('devices', [])
            ]
        except Exception as e:
            log.error(f'Spotify get_devices error: {e}')
            return []

    def transfer(self, device_name: str) -> str:
        """Transfer playback to another device by name."""
        if not self.connected:
            return 'Spotify не е свързан.'
        try:
            self._refresh_token_if_needed()
            devices = self._sp.devices().get('devices', [])
            # Find device by partial name match
            target = None
            for d in devices:
                if device_name.lower() in d['name'].lower():
                    target = d
                    break
            if not target:
                names = [d['name'] for d in devices]
                log.warning(f'Device "{device_name}" not found in: {names}')
                return (f'Устройството "{device_name}" не е намерено. '
                        f'Налични: {", ".join(names)}')
            self._sp.transfer_playback(
                device_id=target['id'],
                force_play=True
            )
            self._device_id = target['id']
            log.info(f'Spotify transferred to: {target["name"]}')
            return f'Музиката е прехвърлена на {target["name"]}.'
        except Exception as e:
            log.error(f'Spotify transfer error: {e}')
            return 'Грешка при прехвърляне.'