import logging
import os
import threading
import spotipy
from spotipy.oauth2 import SpotifyOAuth

_LOGGER = logging.getLogger(__name__)

class SpotifyClient:
    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
        
        self.sp = None
        self.connected = False
        self.original_volume = 75
        self.is_ducked = False
        self._lock = threading.Lock()

        if self.client_id and self.client_secret:
            try:
                cache_path = os.path.join(os.path.dirname(__file__), ".spotify_cache")
                
                # Check if cache exists to avoid blocking prompt
                if not os.path.exists(cache_path):
                    _LOGGER.warning(f"Spotify cache not found at {cache_path}. Run 'python setup_spotify.py' to authenticate.")
                    return

                # Scope for playback control
                scope = "user-modify-playback-state user-read-playback-state"
                self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    redirect_uri=self.redirect_uri,
                    scope=scope,
                    open_browser=False,
                    cache_path=cache_path
                ))
                # Quick check to verify token
                self.sp.current_user()
                self.connected = True
                _LOGGER.info("Spotify connected.")
            except Exception as e:
                _LOGGER.error(f"Spotify connection failed: {e}")
        else:
            _LOGGER.warning("Spotify credentials not found. Integration disabled.")

    def _get_device_id(self):
        """Helper to find the best available device ID."""
        try:
            devices = self.sp.devices()
            if not devices or 'devices' not in devices:
                return None
            
            all_devices = devices['devices']
            _LOGGER.debug(f"Available Spotify devices: {[d['name'] for d in all_devices]}")

            # 1. Prioritize device named "chochko" or "raspotify" (local device)
            #    This ensures the assistant plays on itself, not on a phone that happens to be active.
            for d in all_devices:
                name = d['name'].lower()
                if "chochko" in name or "raspotify" in name:
                    return d['id']

            _LOGGER.warning("Preferred device 'chochko'/'raspotify' not found. Available: %s", [d['name'] for d in all_devices])

            # 2. Prefer active device, else first available
            active_device = next((d for d in all_devices if d['is_active']), None)
            return active_device['id'] if active_device else (all_devices[0]['id'] if all_devices else None)
        except Exception as e:
            _LOGGER.error(f"Error getting device ID: {e}")
            return None

    def play_music(self, query=None):
        if not self.connected: return {"error": "Spotify not connected"}
        
        try:
            device_id = self._get_device_id()

            if not device_id:
                _LOGGER.warning("No Spotify devices found. Is Raspotify running?")
                return {"error": "No Spotify devices found. Check Raspotify service."}

            if query:
                results = self.sp.search(q=query, limit=1, type='track,album,playlist')
                uri = None
                name = ""
                
                if results['tracks']['items']:
                    uri = results['tracks']['items'][0]['uri']
                    name = f"track {results['tracks']['items'][0]['name']}"
                elif results['albums']['items']:
                    uri = results['albums']['items'][0]['uri']
                    name = f"album {results['albums']['items'][0]['name']}"
                elif results['playlists']['items']:
                    uri = results['playlists']['items'][0]['uri']
                    name = f"playlist {results['playlists']['items'][0]['name']}"
                
                if uri:
                    # If it's a track, use uris=[uri], if context (album/playlist), use context_uri
                    if 'track' in uri:
                        self.sp.start_playback(device_id=device_id, uris=[uri])
                    else:
                        self.sp.start_playback(device_id=device_id, context_uri=uri)
                    return {"result": f"Playing {name}"}
                else:
                    return {"error": "No music found"}
            else:
                # Resume playback
                self.sp.start_playback(device_id=device_id)
                return {"result": "Resuming playback"}

        except Exception as e:
            _LOGGER.error(f"Spotify play error: {e}")
            return {"error": str(e)}

    def next_track(self):
        if not self.connected: return {"error": "Spotify not connected"}
        try:
            device_id = self._get_device_id()
            if not device_id: return {"error": "No device found"}
            
            self.sp.next_track(device_id=device_id)
            return {"result": "Skipped to next track"}
        except Exception as e:
            return {"error": str(e)}

    def previous_track(self):
        if not self.connected: return {"error": "Spotify not connected"}
        try:
            device_id = self._get_device_id()
            if not device_id: return {"error": "No device found"}

            self.sp.previous_track(device_id=device_id)
            return {"result": "Skipped to previous track"}
        except Exception as e:
            return {"error": str(e)}

    def duck_volume(self):
        """Lowers volume for voice interaction (non-blocking)."""
        if not self.connected: return
        threading.Thread(target=self._duck_volume_thread, daemon=True).start()

    def _duck_volume_thread(self):
        with self._lock:
            if self.is_ducked: return
            try:
                playback = self.sp.current_playback()
                if playback and playback['is_playing']:
                    current_vol = playback['device']['volume_percent']
                    if current_vol is not None and current_vol > 20:
                        self.original_volume = current_vol
                        self.sp.volume(20)
                        self.is_ducked = True
                        _LOGGER.debug(f"Spotify volume ducked from {current_vol} to 20")
            except spotipy.SpotifyException as e:
                if e.http_status == 403 and "VOLUME_CONTROL_DISALLOW" in str(e):
                    _LOGGER.info("Spotify volume control not allowed on this device. Ducking skipped.")
                else:
                    _LOGGER.error(f"Spotify duck error: {e}")
            except Exception as e:
                _LOGGER.error(f"Spotify duck error: {e}")

    def unduck_volume(self):
        """Restores volume after voice interaction (non-blocking)."""
        if not self.connected: return
        threading.Thread(target=self._unduck_volume_thread, daemon=True).start()

    def _unduck_volume_thread(self):
        with self._lock:
            if not self.is_ducked: return
            try:
                self.sp.volume(self.original_volume)
                self.is_ducked = False
                _LOGGER.debug(f"Spotify volume restored to {self.original_volume}")
            except Exception as e:
                _LOGGER.error(f"Spotify unduck error: {e}")
                self.is_ducked = False