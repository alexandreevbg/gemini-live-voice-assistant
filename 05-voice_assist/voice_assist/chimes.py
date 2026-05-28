import numpy as np
import logging

log = logging.getLogger(__name__)

RATE = 48000

_speaker = None

def set_speaker(spk):
    """Set Speaker instance for playback."""
    global _speaker
    _speaker = spk

def _tone(freq: float, duration: float,
          volume: float = 0.3, fade_ms: int = 10) -> np.ndarray:
    n    = int(RATE * duration)
    t    = np.linspace(0, duration, n, endpoint=False)
    wave = np.sin(2 * np.pi * freq * t).astype(np.float32)
    fade = int(RATE * fade_ms / 1000)
    wave[:fade]  *= np.linspace(0, 1, fade)
    wave[-fade:] *= np.linspace(1, 0, fade)
    return (wave * volume).astype(np.float32)

def _play(segments: list):
    audio = np.concatenate(segments)
    if _speaker:
        _speaker.play_f32(audio)
    else:
        import sounddevice as sd
        stereo = np.stack([audio, audio], axis=1)
        sd.play(stereo, samplerate=RATE, blocking=True)

def wake_detected():
    log.debug('Chime: wake detected')
    _play([
        _tone(880,  0.12),
        _tone(1047, 0.12),
        _tone(1319, 0.18),
    ])

def dialog_ended():
    log.debug('Chime: dialog ended')
    _play([
        _tone(1319, 0.12),
        _tone(1047, 0.12),
        _tone(880,  0.18),
    ])

def error():
    log.debug('Chime: error')
    _play([_tone(220, 0.20)])