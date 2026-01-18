# main.py

import logging
import threading
import queue
import time
import numpy as np
import json
import urllib.request

# Import necessary components
from .openww import embeddings_proc, mels_proc, ww_proc # Added AudioMode
from .gemini_live import GeminiClient
from .spotify_client import SpotifyClient
from .audio import AudioProcessor, AudioMode
from .config_manager import config_manager, CONFIG_FILE_PATH
from .gpio_handler import init_buttons, cleanup_gpio, init_leds, set_led_mode
from .const import (
    State,
    MODELS_DIR,
    WAKE_WORD_MODEL_NAME,
    WAKE_WORD_MODEL_PATH,
    DEBUG_PROBABILITY,
)

# Seconds to wait for Gemini response before switching back to WAKE_WORD
GEMINI_SILENCE_TIMEOUT = 7

DEBUG = False       # Set to True for debugging
if DEBUG:
    log_level = logging.DEBUG
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(threadName)s - %(message)s'
else:
    log_level = logging.INFO
    log_format = '%(levelname)s - %(name)s - %(threadName)s - %(message)s'

logging.basicConfig(level=log_level, format=log_format)

# Suppress noisy websockets debug logs
logging.getLogger("websockets").setLevel(logging.INFO)

_LOGGER = logging.getLogger(__name__)

def get_location():
    """Retrieves location from IP and checks internet connectivity."""
    try:
        with urllib.request.urlopen("http://ip-api.com/json/", timeout=5) as url:
            data = json.loads(url.read().decode())
            return f"{data.get('city')}, {data.get('country')}"
    except Exception as e:
        _LOGGER.error(f"Internet connection check failed: {e}")
        return None

# --- Wake Word Detection Callback ---
def detection_callback(audio_processor: AudioProcessor, gemini_client: GeminiClient, name: str):
    """Called when a wake word is detected."""
    current_mode = audio_processor.get_mode()
    if current_mode != AudioMode.LISTENING:
        _LOGGER.info(f"Wake word detected in {current_mode.name}.")
        
        # Switch to listening (captures audio to stt_audio_queue) and start Gemini
        audio_processor.switch_to_listening() 
        gemini_client.start_session()

# --- Main Function ---
def main():
    _LOGGER.debug("Starting application...")

    config_manager.load()
    _LOGGER.info(f"Configuration loaded from {CONFIG_FILE_PATH}")

    # --- Internet & Location Check ---
    location = get_location()
    if location is None:
        _LOGGER.critical("No internet connection or location service unavailable. Stopping application.")
        return
    _LOGGER.info(f"Location detected: {location}")

    # --- State Initialization ---
    state = State(
        models_dir=MODELS_DIR,
        debug_probability=DEBUG_PROBABILITY,
    )
    
    # --- Spotify Initialization ---
    spotify_client = SpotifyClient()

    # --- Component Initialization ---
    audio_processor = AudioProcessor(
        state,
        on_mode_change=set_led_mode,
        spotify_client=spotify_client
        )
    gemini_client = GeminiClient(location, spotify_client=spotify_client)
    
    # Connect Gemini output to AudioProcessor playback
    gemini_client.set_audio_callback(audio_processor.play_audio)
    gemini_client.set_tool_start_callback(audio_processor.switch_to_execute)
    gemini_client.set_tool_end_callback(audio_processor.switch_to_listening)

    # --- Hardware Initialization ---
    init_leds()
    # Pass the necessary components to the button handler
    # Passing gemini_client to allow buttons to control the session (e.g. stop/mute)
    init_buttons(audio_processor, gemini_client)
    
    # Indicate startup complete
    set_led_mode(AudioMode.WAKE_WORD)

    # --- Thread Creation and Start ---
    threads = []
    thread_names = []

    audio_thread = threading.Thread(
        target=audio_processor.audio_stream, daemon=True, name="AudioStreamThread"
    )
    threads.append(audio_thread)
    thread_names.append("AudioStream")

    mels_thread = threading.Thread(target=mels_proc, args=(state,), daemon=True, name="MelsThread")
    threads.append(mels_thread)
    thread_names.append("Mels")

    ww_thread = threading.Thread(
        target=ww_proc,
        args=(
            state,
            WAKE_WORD_MODEL_NAME,
            str(WAKE_WORD_MODEL_PATH),
            lambda name: detection_callback(audio_processor, gemini_client, name),
        ),
        daemon=True,
        name=f"WWThread-{WAKE_WORD_MODEL_NAME}"
    )
    threads.append(ww_thread)
    thread_names.append(f"WakeWord-{WAKE_WORD_MODEL_NAME}")
    state.ww_threads[WAKE_WORD_MODEL_NAME] = ww_thread

    embeddings_thread = threading.Thread(
        target=embeddings_proc, args=(state,), daemon=True, name="EmbeddingsThread"
    )
    threads.append(embeddings_thread)
    thread_names.append("Embeddings")

    for thread in threads:
        thread.start()

    _LOGGER.info("Ready")

    # --- Gemini Audio Bridge & Logic ---
    def gemini_bridge_loop():
        """Routes audio from AudioProcessor to Gemini and handles interruption logic."""
        
        while state.is_running:
            # Only process if we are effectively in GEMINI mode (which uses LISTENING mode in AudioProcessor)
            # and Gemini is actually connected/connecting.
            if audio_processor.get_mode() == AudioMode.LISTENING:
                try:
                    # Get audio chunk from the queue (timeout allows checking state periodically)
                    chunk = audio_processor.stt_audio_queue.get(timeout=0.1)
                    if chunk is None: continue

                    # Send to Gemini
                    gemini_client.feed_audio(chunk)

                except queue.Empty:
                    pass
            else:
                time.sleep(0.1)

    gemini_thread = threading.Thread(target=gemini_bridge_loop, daemon=True, name="GeminiBridge")
    gemini_thread.start()

    # --- Main Loop ---
    try:
        while state.is_running:
            if not audio_thread.is_alive():
                 _LOGGER.error("Audio stream thread has died. Stopping.")
                 state.is_running = False
                 break
            
            # --- Silence Timeout Logic ---
            # If we are in LISTENING mode (Gemini) for more than GEMINI_SILENCE_TIMEOUT seconds since the last switch,
            # then we assume the interaction is over or timed out, and switch back to WAKE_WORD.
            if audio_processor.get_mode() == AudioMode.LISTENING:
                if time.time() - audio_processor.last_listening_time > GEMINI_SILENCE_TIMEOUT:
                    _LOGGER.info(f"Gemini timeout ({GEMINI_SILENCE_TIMEOUT}s).")
                    gemini_client.stop_session()
                    audio_processor.switch_to_wake_word()

            time.sleep(1)

    except KeyboardInterrupt:
        _LOGGER.info("Stopping due to KeyboardInterrupt...")
        state.is_running = False
    except Exception as e:
        _LOGGER.exception(f"Main loop encountered an error: {e}")
        state.is_running = False
    finally:
        # --- Graceful Shutdown ---
        _LOGGER.info("Shutdown sequence initiated...")
        state.is_running = False
        
        # Release semaphores to unblock threads
        for _ in range(5):
            state.audio_ready.release()
            state.mels_ready.release()
            for ww_state in state.wake_words.values():
                ww_state.embeddings_ready.release()

        try:
            audio_processor.stt_audio_queue.put(None, block=True, timeout=0.5)
        except queue.Full:
            _LOGGER.warning("Could not put sentinel in STT queue during shutdown (queue full).")
        except Exception as e:
            _LOGGER.warning(f"Error putting sentinel in STT queue: {e}")

        all_threads_to_join = threads[:]
        all_thread_names = thread_names[:]

        if gemini_thread.is_alive():
            all_threads_to_join.append(gemini_thread)
            all_thread_names.append(gemini_thread.name)

        if audio_processor.output_thread and audio_processor.output_thread.is_alive():
             all_threads_to_join.append(audio_processor.output_thread)
             all_thread_names.append(audio_processor.output_thread.name)

        for thread, name in zip(all_threads_to_join, all_thread_names):
            _LOGGER.debug(f"Joining {name} thread...")
            thread.join(timeout=2.0)
            if thread.is_alive():
                _LOGGER.warning(f"{name} thread did not exit cleanly after timeout.")

        # Clean up GPIO resources
        cleanup_gpio()

        _LOGGER.info("All threads joined or timed out.")
        _LOGGER.info("Stopped")


if __name__ == "__main__":
    main()
