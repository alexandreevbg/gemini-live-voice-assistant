import logging
import threading
import queue
import ctypes
import os
import sys
import subprocess
import time
import numpy as np
import pyaudio
from enum import Enum, auto

from .const import (
    State,
    ClientData,
    ensure_wake_word_settings,
)
from .config_manager import config_manager

_LOGGER = logging.getLogger(__name__)

# --- ALSA Error Suppression (Moved from gemini_live.py) ---
ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
def py_error_handler(filename, line, function, err, fmt):
    pass
c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

try:
    asound = ctypes.cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(c_error_handler)
except OSError:
    pass
# ----------------------------------------------------------

# Audio Configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
INPUT_SAMPLE_RATE = 16000  # Standard for Wake Word / STT
OUTPUT_SAMPLE_RATE = 24000 # Gemini Output Rate
CHUNK_SIZE_GEMINI = 1024
CHUNK_SIZE_WW = 1280

class AudioMode(Enum):
    WAKE_WORD = auto()
    LISTENING = auto()
    RESPONSE = auto()
    EXECUTE = auto()

class AudioProcessor:
    def __init__(self, state: State, on_mode_change=None, spotify_client=None):
        self.state = state
        self.mode = AudioMode.WAKE_WORD
        self.mode_lock = threading.Lock()
        self.last_listening_time = 0
        self.on_mode_change = on_mode_change
        self.spotify_client = spotify_client
        
        # Queue for sending audio to Gemini (via main.py bridge)
        self.stt_audio_queue = queue.Queue()
        
        # Queue for playing audio from Gemini
        self.output_queue = queue.Queue()
        
        # Initialize PyAudio
        # Suppress JACK/ALSA noise during init
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            old_stderr = os.dup(2)
            sys.stderr.flush()
            os.dup2(devnull, 2)
            os.close(devnull)
            self.pya = pyaudio.PyAudio()
        finally:
            os.dup2(old_stderr, 2)
            os.close(old_stderr)

        self.stream = None
        self.output_stream = None
        self.running = False
        
        # Start output thread
        self.output_thread = threading.Thread(target=self._output_loop, daemon=True, name="AudioOutput")
        self.output_thread.start()

        # Set initial volume from config
        initial_vol = config_manager.get("speaker_volume", 75)
        _LOGGER.info(f"Restoring volume from config: {initial_vol}")
        self.set_volume(initial_vol)

    def get_mode(self):
        with self.mode_lock:
            return self.mode

    def switch_to_listening(self):
        with self.mode_lock:
            self.mode = AudioMode.LISTENING
            self.last_listening_time = time.time()
            # Clear queue to avoid stale audio
            with self.stt_audio_queue.mutex:
                self.stt_audio_queue.queue.clear()
            
            # Clear output queue to stop playback immediately
            with self.output_queue.mutex:
                self.output_queue.queue.clear()
            
            # Reset OpenWakeWord buffers to prevent re-triggering on old audio
            with self.state.clients_lock:
                if "local_mic" in self.state.clients:
                    self.state.clients["local_mic"].reset()

        if self.spotify_client:
            self.spotify_client.duck_volume()

        if self.on_mode_change:
            self.on_mode_change(self.mode)

    def reset_listening_timestamp(self):
        """Resets the timeout timer for LISTENING mode."""
        self.last_listening_time = time.time()

    def switch_to_response(self):
        with self.mode_lock:
            self.mode = AudioMode.RESPONSE

        if self.spotify_client:
            self.spotify_client.duck_volume()

        if self.on_mode_change:
            self.on_mode_change(self.mode)

    def switch_to_wake_word(self):
        with self.mode_lock:
            self.mode = AudioMode.WAKE_WORD
            # Clear output queue to stop playback immediately
            with self.output_queue.mutex:
                self.output_queue.queue.clear()

        if self.spotify_client:
            self.spotify_client.unduck_volume()

        if self.on_mode_change:
            self.on_mode_change(self.mode)

    def switch_to_execute(self):
        with self.mode_lock:
            self.mode = AudioMode.EXECUTE
            
        if self.spotify_client:
            self.spotify_client.duck_volume()
            
        if self.on_mode_change:
            self.on_mode_change(self.mode)

    def play_audio(self, chunk):
        """Adds audio chunk to the playback queue."""
        # If we are in WAKE_WORD, receiving audio should wake us up to LISTENING
        # before playback starts (which switches to RESPONSE).
        if self.get_mode() == AudioMode.WAKE_WORD:
            self.switch_to_listening()
        self.output_queue.put(chunk)

    def set_volume(self, volume: int):
        """Sets the system volume (0-100)."""
        try:
            volume = int(volume)
            volume = max(0, min(100, volume))
            subprocess.run(["amixer", "-q", "-M", "sset", "Speaker", f"{volume}%", "unmute"], check=False, stderr=subprocess.DEVNULL)
            config_manager.set("speaker_volume", volume)
            config_manager.save()
            _LOGGER.debug(f"Volume set to {volume}%")
        except Exception as e:
            _LOGGER.error(f"Error setting volume: {e}")

    def get_volume(self) -> int:
        return config_manager.get("speaker_volume", 75)

    def louder(self):
        vol = self.get_volume()
        self.set_volume(vol + 5)

    def quieter(self):
        vol = self.get_volume()
        self.set_volume(vol - 5)

    def _output_loop(self):
        """Handles audio playback and mode switching for RESPONSE."""
        # Retry opening stream to handle temporary device busy states
        while self.state.is_running and self.output_stream is None:
            try:
                self.output_stream = self.pya.open(
                    format=FORMAT,
                    channels=CHANNELS,
                    rate=OUTPUT_SAMPLE_RATE,
                    output=True,
                )
            except Exception as e:
                _LOGGER.error(f"Failed to open audio output stream: {e}. Retrying in 2s...")
                time.sleep(2)
        
        while self.state.is_running:
            try:
                # Wait for audio data
                # Using a timeout allows us to check if we should switch back to LISTENING
                chunk = self.output_queue.get(timeout=0.1)
                
                # If we have data, ensure we are in RESPONSE mode
                if self.get_mode() != AudioMode.RESPONSE:
                    self.switch_to_response()
                
                self.output_stream.write(chunk)
                
            except queue.Empty:
                # Queue is empty, if we were in RESPONSE mode, switch back to LISTENING
                if self.get_mode() == AudioMode.RESPONSE:
                    self.switch_to_listening()
            except Exception as e:
                _LOGGER.error(f"Error in output loop: {e}")
                time.sleep(0.1)

    def audio_stream(self):
        """Captures audio from microphone and routes based on mode."""
        _LOGGER.info("Starting audio stream...")
        self.running = True
        
        try:
            self.stream = self.pya.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=INPUT_SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE_GEMINI,
            )

            client_id = "local_mic"
            
            # Initialize client data for OpenWakeWord
            with self.state.clients_lock:
                if client_id not in self.state.clients:
                    client_data = ClientData()
                    for ww_name in self.state.wake_words:
                        ensure_wake_word_settings(client_data, ww_name)
                    self.state.clients[client_id] = client_data

            while self.state.is_running and self.running:
                try:
                    current_mode = self.get_mode()
                    # Use WW chunk size for wake word and interruption, otherwise use Gemini's chunk size.
                    read_size = CHUNK_SIZE_GEMINI if current_mode == AudioMode.LISTENING else CHUNK_SIZE_WW

                    data = self.stream.read(read_size, exception_on_overflow=False)
                except OSError as e:
                    _LOGGER.error(f"Audio read error: {e}")
                    time.sleep(0.1)
                    continue

                if current_mode == AudioMode.WAKE_WORD or current_mode == AudioMode.RESPONSE or current_mode == AudioMode.EXECUTE:
                    # Route to OpenWakeWord
                    # Convert bytes to float32 for OpenWakeWord (16-bit PCM -> float32)
                    audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    
                    with self.state.clients_lock:
                        if client_id in self.state.clients:
                            client = self.state.clients[client_id]
                            
                            # Use rolling buffer: shift left and append new data
                            shift = len(audio_data)
                            client.audio = np.roll(client.audio, -shift)
                            client.audio[-shift:] = audio_data
                            
                            client.new_audio_samples = min(client.new_audio_samples + shift, len(client.audio))
                            client.audio_timestamp = int(time.time() * 1000)
                    
                    # Signal that audio is ready for processing
                    self.state.audio_ready.release()

                elif current_mode == AudioMode.LISTENING:
                    # Route to Gemini (via queue)
                    # Gemini expects raw bytes (PCM)
                    self.stt_audio_queue.put(data)

        except Exception as e:
            _LOGGER.exception(f"Error in audio stream: {e}")
        finally:
            self.running = False
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            if self.output_stream:
                self.output_stream.close()
            self.pya.terminate()
            _LOGGER.info("Audio stream stopped")