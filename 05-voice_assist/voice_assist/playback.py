import sounddevice as sd
import numpy as np
import scipy.signal
import queue
import logging

log = logging.getLogger(__name__)

RATE      = 48000
BLOCKSIZE = 1024

class Speaker:
    def __init__(self):
        self._queue     = queue.Queue(maxsize=2000)
        self._stream    = None
        self._running   = False
        self._ref_buf   = queue.Queue(maxsize=2000)
        self._silence   = np.zeros(BLOCKSIZE, dtype=np.float32)
        self._remainder = np.array([], dtype=np.float32)

    def get_reference(self) -> np.ndarray:
        try:
            return self._ref_buf.get_nowait()
        except queue.Empty:
            return self._silence

    def play_gemini(self, pcm_24k_bytes: bytes):
        arr_24k  = np.frombuffer(pcm_24k_bytes, dtype=np.int16).astype(np.float32)
        arr_48k  = scipy.signal.resample_poly(arr_24k, 2, 1)
        arr_norm = arr_48k / 32767.0
        self._enqueue_seamless(arr_norm)

    def play_f32(self, audio_f32: np.ndarray):
        self._enqueue_seamless(audio_f32)

    def clear(self):
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._remainder = np.array([], dtype=np.float32)

    def start(self):
        import config
        self._running = True
        self._stream  = sd.OutputStream(
            device=config.PIPEWIRE_DEVICE,
            samplerate=RATE,
            channels=2,
            dtype='float32',
            blocksize=BLOCKSIZE,
            callback=self._callback,
        )
        self._stream.start()
        log.info('Speaker started')

    def stop(self):
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                log.warning(f'Speaker stop error: {e}')
            self._stream = None
        self.clear()
        log.info('Speaker stopped')

    def _enqueue_seamless(self, audio: np.ndarray):
        if len(self._remainder) > 0:
            audio = np.concatenate([self._remainder, audio])
        n_blocks = len(audio) // BLOCKSIZE
        for i in range(n_blocks):
            block = audio[i*BLOCKSIZE:(i+1)*BLOCKSIZE].astype(np.float32)
            try:
                self._queue.put_nowait(block)
            except queue.Full:
                log.warning('Speaker queue full — dropping')
        self._remainder = audio[n_blocks*BLOCKSIZE:].copy()

    def _callback(self, outdata, frames, time_info, status):
        if status:
            log.warning(f'Speaker: {status}')
        try:
            chunk = self._queue.get_nowait()
        except queue.Empty:
            chunk = self._silence
        try:
            self._ref_buf.put_nowait(chunk.copy())
        except queue.Full:
            pass
        outdata[:, 0] = chunk
        outdata[:, 1] = chunk