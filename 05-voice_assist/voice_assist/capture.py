import sounddevice as sd
import numpy as np
import scipy.signal
import threading
import logging

log = logging.getLogger(__name__)

RATE_HW   = 48000
RATE_APP  = 16000
CHUNK_APP = 1280
CHUNK_HW  = int(CHUNK_APP * RATE_HW / RATE_APP)  # 3840

class MicCapture:
    def __init__(self):
        self._consumers = []
        self._lock      = threading.Lock()
        self._stream    = None
        self._muted     = False

    def add_consumer(self, fn):
        with self._lock:
            self._consumers.append(fn)

    def remove_consumer(self, fn):
        with self._lock:
            if fn in self._consumers:
                self._consumers.remove(fn)

    def clear_consumers(self):
        with self._lock:
            self._consumers.clear()

    def set_mute(self, muted: bool):
        self._muted = muted

    def start(self):
        import config
        self._stream = sd.InputStream(
            device=config.PIPEWIRE_DEVICE,
            samplerate=RATE_HW,
            channels=1,           # AEC Source is mono
            dtype='int32',
            blocksize=CHUNK_HW,
            callback=self._callback,
        )
        self._stream.start()
        log.info(f'MicCapture started: mono {RATE_HW}Hz → {RATE_APP}Hz blocksize={CHUNK_HW}')

    def stop(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                log.warning(f'MicCapture stop error: {e}')
            self._stream = None
        log.info('MicCapture stopped')

    def _callback(self, indata, frames, time_info, status):
        if status:
            log.warning(f'MicCapture: {status}')
        if self._muted:
            return

        # AEC Source: mono int32 → float32
        mono_f32 = indata[:, 0].astype(np.float32) / 2147483648.0

        # Resample 48kHz → 16kHz
        mono_16k = scipy.signal.resample_poly(mono_f32, 1, 3)

        # Convert to int16 for openWakeWord + Gemini
        mono_i16 = (mono_16k * 32767).astype(np.int16)

        with self._lock:
            for fn in list(self._consumers):
                try:
                    fn(mono_i16)
                except Exception as e:
                    log.error(f'Consumer error: {e}')