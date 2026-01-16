from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Final, Optional, Set, Tuple, Any
from threading import Lock, Semaphore, Thread, RLock # Added for State class

import numpy as np

_DIR = Path(__file__).parent
MODELS_DIR: Path = _DIR / "models"
WAKE_WORD_MODEL_NAME = "chohchkoh"
WAKE_WORD_MODEL_PATH: Path = MODELS_DIR / f"{WAKE_WORD_MODEL_NAME}.tflite"
THRESHOLD = 0.1
TRIGGER_LEVEL = 1
DEBUG_PROBABILITY = False
OUTPUT_DIR = _DIR / "output"
AUDIO_RATE = 16000
AUDIO_WIDTH = 2  # 16-bit
SAMPLES_PER_CHUNK = 1280

_AUTOFILL_SECONDS: Final = 8
_MAX_SECONDS: Final = 10

_SAMPLE_RATE: Final = 16000  # 16Khz
_SAMPLE_WIDTH: Final = 2  # 16-bit samples
_MAX_SAMPLES: Final = _MAX_SECONDS * _SAMPLE_RATE

MS_PER_CHUNK: Final = 80
DEFAULT_PIPEWIRE_CAPTURE_NODE: Final = "alsa_input.platform-soc_sound.stereo-fallback"
DEFAULT_TTS_PIPEWIRE_SINK: Final = "alsa_output.platform-soc_sound.stereo-fallback"

# window = 400, hop length = 160
_MELS_PER_SECOND: Final = 12
_MAX_MELS: Final = _MAX_SECONDS * _MELS_PER_SECOND
MEL_SAMPLES: Final = 1280
NUM_MELS: Final = 32

EMB_FEATURES: Final = 76  # 775 ms
EMB_STEP: Final = 8
_MAX_EMB: Final = 100
WW_FEATURES: Final = 96

CLIENT_ID_TYPE = Tuple[str, int]

@dataclass
class WakeWordData:
    threshold: float = 0.5
    trigger_level: int = 1
    new_embeddings: int = 0
    embeddings_timestamp: int = 0
    embeddings: np.ndarray = field(
        default_factory=lambda: np.zeros(
            shape=(_MAX_EMB, WW_FEATURES), dtype=np.float32
        )
    )
    activations: int = 0
    is_detected: bool = False
    ww_windows: Optional[int] = None

@dataclass
class ClientData:
    new_audio_samples: int = _AUTOFILL_SECONDS * _SAMPLE_RATE
    audio_timestamp: int = 0
    audio: np.ndarray = field(
        default_factory=lambda: np.zeros(shape=(_MAX_SAMPLES,), dtype=np.float32)
    )
    new_mels: int = 0
    mels_timestamp: int = 0
    mels: np.ndarray = field(
        default_factory=lambda: np.zeros(shape=(_MAX_MELS, NUM_MELS), dtype=np.float32)
    )
    wake_words: Dict[str, WakeWordData] = field(default_factory=dict)
    wake_word_names: Optional[Set[str]] = None

    def reset(self) -> None:
        self.audio.fill(0)
        self.new_audio_samples = _AUTOFILL_SECONDS * _SAMPLE_RATE
        self.mels.fill(0)
        self.new_mels = 0
        for ww_data in self.wake_words.values():
            ww_data.embeddings.fill(0)
            ww_data.new_embeddings = 0
            ww_data.is_detected = False
            ww_data.activations = 0
            ww_data.ww_windows = None

# --- State related dataclasses (moved from state.py) ---
@dataclass
class WakeWordState:
    embeddings_ready: Semaphore = field(default_factory=lambda: Semaphore(0))
    embeddings_lock: Lock = field(default_factory=Lock)
    is_processing: bool = False # Renamed from is_detected for clarity

@dataclass
class State:
    models_dir: Path
    debug_probability: bool = False

    ww_threads: Dict[str, Thread] = field(default_factory=dict)
    ww_threads_lock: Lock = field(default_factory=Lock)

    is_running: bool = True
    clients: Dict[str, ClientData] = field(default_factory=dict)
    clients_lock: RLock = field(default_factory=RLock)

    audio_lock: Lock = field(default_factory=Lock)
    mels_lock: Lock = field(default_factory=Lock)
    audio_ready: Semaphore = field(default_factory=lambda: Semaphore(0))
    mels_ready: Semaphore = field(default_factory=lambda: Semaphore(0))

    # full name -> state
    wake_words: Dict[str, WakeWordState] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize default model and client settings after object creation."""
        # Load default wake word model state
        self.load_model(WAKE_WORD_MODEL_NAME)
        
        # Initialize default client
        if "default" not in self.clients:
            self.clients["default"] = ClientData()
        
        # Ensure wake word settings for the default client and model
        ensure_wake_word_settings(
            client_data=self.clients["default"],
            model_name=WAKE_WORD_MODEL_NAME
        )
        _LOGGER.info("Default model and client settings initialized in State.")

    def load_model(self, model_name: str):
        """Loads a wake word model state entry."""
        if model_name not in self.wake_words:
            self.wake_words[model_name] = WakeWordState()
            _LOGGER.debug(f"Initialized WakeWordState for model: {model_name}")
        else:
            _LOGGER.debug(f"WakeWordState for model: {model_name} already exists.")

def ensure_wake_word_settings(client_data: ClientData, model_name: str):
    """
    Ensures that WakeWordData exists for the given model_name in client_data
    and is initialized/updated with the global THRESHOLD and TRIGGER_LEVEL.
    """
    if model_name not in client_data.wake_words:
        client_data.wake_words[model_name] = WakeWordData(
            threshold=THRESHOLD, trigger_level=TRIGGER_LEVEL
        )
    else:
        # Ensure existing settings are updated if constants change (e.g., during development)
        client_data.wake_words[model_name].threshold = THRESHOLD
        client_data.wake_words[model_name].trigger_level = TRIGGER_LEVEL

# Logger for const.py, especially for State initialization
import logging # Add logging import here for _LOGGER in State
_LOGGER = logging.getLogger(__name__)