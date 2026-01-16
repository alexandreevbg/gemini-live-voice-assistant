from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, Semaphore, Thread
from typing import Dict
from .const import ClientData, WakeWordData
import logging

_LOGGER = logging.getLogger(__name__)

@dataclass
class WakeWordState:
    embeddings_ready: Semaphore = field(default_factory=lambda: Semaphore(0))
    embeddings_lock: Lock = field(default_factory=Lock)
    is_detected: bool = False


@dataclass
class State:
    models_dir: Path
    """Directory with built-in models."""

    ww_threads: Dict[str, Thread] = field(default_factory=dict)
    ww_threads_lock: Lock = field(default_factory=Lock)

    is_running: bool = True
    clients: Dict[str, ClientData] = field(default_factory=dict)
    clients_lock: Lock = field(default_factory=Lock)

    audio_lock: Lock = field(default_factory=Lock)
    mels_lock: Lock = field(default_factory=Lock)
    audio_ready: Semaphore = field(default_factory=lambda: Semaphore(0))
    mels_ready: Semaphore = field(default_factory=lambda: Semaphore(0))

    # full name -> state
    wake_words: Dict[str, WakeWordState] = field(default_factory=dict)

    debug_probability: bool = False
    #output_dir: Path = None # Removed
    def load_model(self, model_name: str):
        """Loads a wake word model."""
        ww_state = WakeWordState()
        self.wake_words[model_name] = ww_state
        _LOGGER.debug(f"Loaded model: {model_name}")
