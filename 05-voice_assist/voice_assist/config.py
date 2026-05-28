import os
import location as loc_module
import sounddevice as sd

def _find_pipewire_device() -> int:
    """Find PipeWire device index dynamically."""
    for i, d in enumerate(sd.query_devices()):
        if 'pipewire' in d['name'].lower():
            return i
    # Fallback to default
    return sd.default.device[0]

# ── Audio ─────────────────────────────────────────────────
PIPEWIRE_DEVICE = _find_pipewire_device()
RATE_HW          = 48000
RATE_APP         = 16000
CHUNK_APP        = 1280
CHUNK_HW         = int(CHUNK_APP * RATE_HW / RATE_APP)  # 3840

# ── Wake Word ─────────────────────────────────────────────
WAKEWORD_MODEL   = '/home/chochko/voiceAssist/models/chochko.tflite'
WAKEWORD_THRESH  = 0.5

# ── Location ──────────────────────────────────────────────
_location = loc_module.get_current()
_loc_str  = loc_module.format_for_prompt(_location)

# ── Gemini ────────────────────────────────────────────────
GEMINI_API_KEY   = os.environ['GEMINI_API_KEY']
GEMINI_MODEL     = 'models/gemini-2.5-flash-native-audio-latest'
GEMINI_VOICE     = 'Aoede'
GEMINI_LANGUAGE  = None
GEMINI_SYSTEM    = (
    'Ти си приятелски домашен асистент. '
    'Името ти е Чочко. '
    'Давай кратки отговори подходящи за гласов интерфейс. '
    'Когато разказваш приказка, добави 2-3 детайлa, специфични за текущото населеното място. '
    'Когато те питат колко е часът, отговаряй с местното време за текущото местоположение. '
    'Можеш да управляваш музиката в Spotify. '
    + _loc_str
)

# ── Spotify ───────────────────────────────────────────────
SPOTIFY_CLIENT_ID     = os.environ['SPOTIFY_CLIENT_ID']
SPOTIFY_CLIENT_SECRET = os.environ['SPOTIFY_CLIENT_SECRET']
SPOTIFY_REDIRECT_URI  = 'http://127.0.0.1:8888/callback'

# ── Dialog ────────────────────────────────────────────────
DIALOG_TIMEOUT   = 10

# ── Hardware ──────────────────────────────────────────────
BUTTON_PIN       = 17
LINE_DAC         = 66