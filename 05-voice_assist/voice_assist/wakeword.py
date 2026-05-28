import time
import numpy as np
import scipy.signal
import logging
import asyncio
from openwakeword.model import Model

log = logging.getLogger(__name__)

RATE_HW   = 48000
RATE_OWW  = 16000
CHUNK_APP = 1280
HW_CHUNK  = int(CHUNK_APP * RATE_HW / RATE_OWW)

class WakeWordDetector:
    def __init__(self, model_path: str, threshold: float = 0.5):
        self.chunk      = HW_CHUNK
        self.threshold  = threshold
        self._detected  = False
        self._on_detect = None
        self._loop      = None
        self._ready_at  = 0.0

        self._model = Model(
            wakeword_models=[model_path],
            inference_framework='tflite'
        )
        self._model_name = list(self._model.models.keys())[0]
        log.info(f'WakeWordDetector ready: {self._model_name} threshold={threshold}')

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def set_on_detect(self, fn):
        self._on_detect = fn

    def process(self, pcm_i16: np.ndarray):
        if self._detected:
            return
        if time.time() < self._ready_at:
            return

        pred  = self._model.predict(pcm_i16)
        score = float(pred.get(self._model_name, 0))

        if score > self.threshold:
            log.debug(f'Wake word detected! score={score:.3f}')
            self._detected = True
            if self._on_detect and self._loop:
                self._loop.call_soon_threadsafe(self._on_detect)

    def reset(self, cooldown: float = 1.0):
        """
        Clear all internal buffers + ignore detections for cooldown seconds.
        Called during dialog_ended chime — no extra delay added.
        """
        self._detected = False
        self._ready_at = time.time() + cooldown
        self._model.reset()   # clears mel spectrogram + prediction buffers
        log.debug(f'WakeWordDetector reset — cooldown {cooldown}s')