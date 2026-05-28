import numpy as np
import scipy.signal
import logging
import asyncio
from openwakeword.model import Model

log = logging.getLogger(__name__)

RATE_HW  = 48000   # PipeWire AEC rate
RATE_OWW = 16000   # openWakeWord required rate
CHUNK    = 1280    # samples at 16kHz = 80ms
HW_CHUNK = int(CHUNK * RATE_HW / RATE_OWW)  # 3840 at 48kHz
THRESHOLD = 0.5

class WakeWordDetector:
    def __init__(self, model_path: str, threshold: float = THRESHOLD):
        self.chunk      = HW_CHUNK
        self.threshold  = threshold
        self._detected  = False
        self._on_detect = None
        self._loop      = None

        self._model = Model(
            wakeword_models=[model_path],
            inference_framework='tflite'
        )
        self._model_name = list(self._model.models.keys())[0]
        log.info(f"WakeWordDetector ready: model={self._model_name} "
                 f"threshold={threshold}")

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def set_on_detect(self, fn):
        self._on_detect = fn

    def process(self, indata: np.ndarray):
        """
        Called by sounddevice InputStream callback.
        indata: stereo int32 @ 48kHz shape=(HW_CHUNK, 2)
        """
        if self._detected:
            return

        # Downmix stereo int32 → mono float32
        mono_f32 = (indata[:,0].astype(np.float32) +
                    indata[:,1].astype(np.float32)) / 2.0 / 2147483648.0

        # Resample 48kHz → 16kHz
        mono_16k = scipy.signal.resample_poly(mono_f32, 1, 3)

        # Convert to int16
        mono_i16 = (mono_16k * 32767).astype(np.int16)

        # Run detection
        pred  = self._model.predict(mono_i16)
        score = float(pred.get(self._model_name, 0))

        if score > self.threshold:
            log.debug(f"Wake word detected! score={score:.3f}")
            self._detected = True
            if self._on_detect and self._loop:
                self._loop.call_soon_threadsafe(self._on_detect)

    def reset(self):
        self._detected = False
        log.debug("WakeWordDetector reset")

    @property
    def hw_chunk(self):
        return HW_CHUNK
