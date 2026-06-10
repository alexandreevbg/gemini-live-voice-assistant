import time
import logging
import asyncio
import numpy as np
from pathlib import Path

log = logging.getLogger(__name__)
 
RATE_HW   = 48000
RATE_OWW  = 16000
CHUNK_APP = 1280
HW_CHUNK  = 1280  # int16 @ 16kHz arrives from MicCapture


class WakeWordDetector:
    """Base class - same interface for both backends."""

    def __init__(self, model_path: str, threshold: float = 0.5):
        self.chunk      = HW_CHUNK
        self.threshold  = threshold
        self._detected  = False
        self._ready_at  = 0.0
        self._on_detect = None
        self._loop      = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def set_on_detect(self, fn):
        self._on_detect = fn

    def _fire(self):
        self._detected = True
        if self._on_detect and self._loop:
            self._loop.call_soon_threadsafe(self._on_detect)

    def process(self, pcm: np.ndarray):
        raise NotImplementedError

    def reset(self, cooldown: float = 1.0):
        self._detected = False
        self._ready_at = time.time() + cooldown
        self._reset_model()
        log.info(f'WakeWordDetector reset - cooldown {cooldown}s')

    def _reset_model(self):
        raise NotImplementedError

    def _resample(self, pcm: np.ndarray) -> np.ndarray:
        """Audio arrives already as int16 at 16kHz from MicCapture."""
        return pcm.astype('int16')


class OpenWakeWordDetector(WakeWordDetector):
    """openWakeWord backend."""

    def __init__(self, model_path: str, threshold: float = 0.5):
        super().__init__(model_path, threshold)
        from openwakeword.model import Model
        self._model = Model(
            wakeword_models=[model_path],
            inference_framework='tflite'
        )
        self._model_name = list(self._model.models.keys())[0]
        log.info(f'openWakeWord ready: {self._model_name} threshold={threshold}')

    def process(self, pcm_16k_i16: np.ndarray):
        if self._detected or time.time() < self._ready_at:
            return
        pcm_16k = self._resample(pcm_16k_i16)
        pred    = self._model.predict(pcm_16k)
        score   = float(pred.get(self._model_name, 0))
        if score > 0.3:
            log.info(f'openWakeWord score: {score:.3f}')
        if score > self.threshold:
            log.info(f'Wake word detected! score={score:.3f}')
            self._fire()

    def _reset_model(self):
        self._model.reset()


class MicroWakeWordDetector(WakeWordDetector):
    """microWakeWord backend via pymicro_wakeword.

    pymicro_wakeword handles the parts that are easy to get wrong:
      * int8 input/output quantization (reads scale/zero_point from the model)
      * the streaming input shape [1, stride, 40] and internal model state
      * 10 ms (160-sample) feature framing
      * sliding-window probability averaging vs. the model's probability_cutoff
    So we just feed it 16 kHz / 16-bit mono audio and read a probability back.
    """

    def __init__(self, model_path: str, threshold: float = 0.5):
        super().__init__(model_path, threshold)
        from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures

        # from_config() expects the JSON manifest, not the .tflite.
        p = Path(model_path)
        config_path = p if p.suffix == '.json' else p.with_suffix('.json')
        if not config_path.exists():
            raise FileNotFoundError(
                f'microWakeWord JSON manifest not found: {config_path}. '
                f'Point WAKEWORD_MODEL_MWW at the .json manifest (and make sure '
                f'its "model" field names the .tflite sitting next to it).'
            )

        self._mww  = MicroWakeWord.from_config(config_path)
        self._feat = MicroWakeWordFeatures()
        # The model author calibrates this; honour it over the generic threshold.
        self._cutoff = self._mww.probability_cutoff

        # API drift across pymicro_wakeword versions:
        #   >= 2.3.0 : process_streaming_prob(feat) -> Optional[float]  (gives score)
        #   2.0-2.2  : process_streaming(feat)      -> bool             (decision only)
        self._has_prob = hasattr(self._mww, 'process_streaming_prob')

        log.info(
            f'microWakeWord ready: "{self._mww.wake_word}" '
            f'cutoff={self._cutoff} window={self._mww.sliding_window_size} '
            f'stride={getattr(self._mww, "stride", "?")} '
            f'score_api={self._has_prob}'
        )

    def process(self, pcm_16k_i16: np.ndarray):
        if self._detected or time.time() < self._ready_at:
            return

        audio_bytes = pcm_16k_i16.astype('int16').tobytes()

        for feat in self._feat.process_streaming(audio_bytes):
            if self._has_prob:
                prob = self._mww.process_streaming_prob(feat)
                if prob is None:
                    continue
                if prob > 0.3:
                    log.info(f'microWakeWord score: {prob:.3f}')
                detected = prob > self._cutoff
            else:
                # Older API: returns the decision directly (cutoff applied inside).
                detected = bool(self._mww.process_streaming(feat))

            if detected:
                log.info('microWakeWord detected!')
                self._fire()
                return

    def _reset_model(self):
        # Reload the model to clear streaming state, and reset the feature buffer.
        from pymicro_wakeword import MicroWakeWordFeatures
        self._mww.reset()
        self._feat = MicroWakeWordFeatures()


def create_detector(backend: str, model_path: str,
                    threshold: float = 0.5) -> WakeWordDetector:
    """Factory - create detector based on backend name."""
    if backend == 'microwakeword':
        return MicroWakeWordDetector(model_path, threshold)
    elif backend == 'openwakeword':
        return OpenWakeWordDetector(model_path, threshold)
    else:
        raise ValueError(
            f'Unknown backend: {backend}. '
            f'Use "openwakeword" or "microwakeword"'
        )
